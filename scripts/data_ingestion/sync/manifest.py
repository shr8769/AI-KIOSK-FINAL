#!/usr/bin/env python3
"""
manifest.py

Synchronization manifest manager for the knowledge sync pipeline.
The manifest is the central state store that drives incremental updates.
It tracks every URL ever crawled, its content hash, associated markdown file,
chunk IDs in ChromaDB, and sync status.

Persistence: JSON file with atomic writes (temp file + rename).
"""

import json
import logging
import os
import tempfile
import time
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("sync.manifest")

IST = timezone(timedelta(hours=5, minutes=30))


class ManifestEntry:
    """Represents a single URL entry in the sync manifest."""

    __slots__ = [
        "url", "canonical_url", "last_crawl_time", "last_modified",
        "content_hash", "markdown_path", "markdown_hash", "category",
        "collection", "chunk_ids", "status", "http_status", "title",
        "error_message", "scraper_version", "ingestion_version",
        "crawl_count", "first_seen",
    ]

    def __init__(
        self,
        url: str,
        canonical_url: str = "",
        last_crawl_time: str = "",
        last_modified: str = "",
        content_hash: str = "",
        markdown_path: str = "",
        markdown_hash: str = "",
        category: str = "",
        collection: str = "",
        chunk_ids: Optional[List[str]] = None,
        status: str = "active",
        http_status: int = 0,
        title: str = "",
        error_message: str = "",
        scraper_version: str = "",
        ingestion_version: str = "",
        crawl_count: int = 0,
        first_seen: str = "",
    ):
        self.url = url
        self.canonical_url = canonical_url or url
        self.last_crawl_time = last_crawl_time
        self.last_modified = last_modified
        self.content_hash = content_hash
        self.markdown_path = markdown_path
        self.markdown_hash = markdown_hash
        self.category = category
        self.collection = collection
        self.chunk_ids = chunk_ids if chunk_ids is not None else []
        self.status = status
        self.http_status = http_status
        self.title = title
        self.error_message = error_message
        self.scraper_version = scraper_version
        self.ingestion_version = ingestion_version
        self.crawl_count = crawl_count
        self.first_seen = first_seen or datetime.now(IST).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize entry to a dictionary."""
        return {
            "url": self.url,
            "canonical_url": self.canonical_url,
            "last_crawl_time": self.last_crawl_time,
            "last_modified": self.last_modified,
            "content_hash": self.content_hash,
            "markdown_path": self.markdown_path,
            "markdown_hash": self.markdown_hash,
            "category": self.category,
            "collection": self.collection,
            "chunk_ids": self.chunk_ids,
            "status": self.status,
            "http_status": self.http_status,
            "title": self.title,
            "error_message": self.error_message,
            "scraper_version": self.scraper_version,
            "ingestion_version": self.ingestion_version,
            "crawl_count": self.crawl_count,
            "first_seen": self.first_seen,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManifestEntry":
        """Deserialize from a dictionary."""
        return cls(
            url=data.get("url", ""),
            canonical_url=data.get("canonical_url", ""),
            last_crawl_time=data.get("last_crawl_time", ""),
            last_modified=data.get("last_modified", ""),
            content_hash=data.get("content_hash", ""),
            markdown_path=data.get("markdown_path", ""),
            markdown_hash=data.get("markdown_hash", ""),
            category=data.get("category", ""),
            collection=data.get("collection", ""),
            chunk_ids=data.get("chunk_ids", []),
            status=data.get("status", "active"),
            http_status=data.get("http_status", 0),
            title=data.get("title", ""),
            error_message=data.get("error_message", ""),
            scraper_version=data.get("scraper_version", ""),
            ingestion_version=data.get("ingestion_version", ""),
            crawl_count=data.get("crawl_count", 0),
            first_seen=data.get("first_seen", ""),
        )


class SyncManifest:
    """
    Central state store for the knowledge sync pipeline.

    The manifest tracks every URL, its content fingerprint, associated files,
    and vector chunk IDs. It is the single source of truth for incremental sync.
    """

    def __init__(self, manifest_path: str = "sync_manifest.json"):
        self.manifest_path = Path(manifest_path)
        self._entries: Dict[str, ManifestEntry] = {}  # keyed by canonical URL
        self._metadata: Dict[str, Any] = {
            "version": "2.0.0",
            "created": "",
            "last_sync_time": "",
            "last_sync_run_id": "",
            "total_syncs": 0,
        }
        self._dirty = False

    # ── Persistence ──────────────────────────────────

    def load(self) -> bool:
        """
        Load manifest from disk. Returns True if loaded successfully,
        False if file doesn't exist (fresh start).
        """
        if not self.manifest_path.exists():
            logger.info(f"No manifest found at {self.manifest_path}. Starting fresh.")
            self._metadata["created"] = datetime.now(IST).isoformat()
            return False

        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._metadata = data.get("metadata", self._metadata)
            entries_data = data.get("entries", {})

            self._entries = {}
            for canonical_url, entry_dict in entries_data.items():
                self._entries[canonical_url] = ManifestEntry.from_dict(entry_dict)

            logger.info(
                f"Manifest loaded: {len(self._entries)} entries, "
                f"last sync: {self._metadata.get('last_sync_time', 'never')}"
            )
            return True

        except json.JSONDecodeError as e:
            logger.error(f"Corrupt manifest file at {self.manifest_path}: {e}")
            # Back up corrupt file and start fresh
            backup_path = self.manifest_path.with_suffix(".json.bak")
            self.manifest_path.rename(backup_path)
            logger.warning(f"Corrupt manifest backed up to {backup_path}. Starting fresh.")
            self._metadata["created"] = datetime.now(IST).isoformat()
            return False
        except Exception as e:
            logger.error(f"Failed to load manifest: {e}")
            return False

    def save(self) -> bool:
        """
        Persist manifest to disk using atomic write (temp file + rename).
        Returns True on success.
        """
        data = {
            "metadata": self._metadata,
            "entries": {
                url: entry.to_dict()
                for url, entry in self._entries.items()
            },
        }

        try:
            # Atomic write: write to temp file, then rename
            parent_dir = self.manifest_path.parent
            parent_dir.mkdir(parents=True, exist_ok=True)

            fd, tmp_path = tempfile.mkstemp(
                suffix=".tmp",
                prefix="sync_manifest_",
                dir=str(parent_dir),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                # On Windows, we need to remove the target first
                if self.manifest_path.exists():
                    self.manifest_path.unlink()
                os.rename(tmp_path, str(self.manifest_path))
            except Exception:
                # Clean up temp file on failure
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

            self._dirty = False
            logger.info(f"Manifest saved: {len(self._entries)} entries to {self.manifest_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save manifest: {e}")
            return False

    # ── Entry Operations ─────────────────────────────

    def get_entry(self, canonical_url: str) -> Optional[ManifestEntry]:
        """Lookup by canonical URL."""
        return self._entries.get(canonical_url)

    def has_entry(self, canonical_url: str) -> bool:
        """Check if a URL exists in the manifest."""
        return canonical_url in self._entries

    def set_entry(self, entry: ManifestEntry) -> None:
        """Add or replace a manifest entry."""
        self._entries[entry.canonical_url] = entry
        self._dirty = True

    def update_entry(self, canonical_url: str, **fields) -> bool:
        """
        Partial update of an existing manifest entry.
        Returns False if entry not found.
        """
        entry = self._entries.get(canonical_url)
        if not entry:
            return False
        for key, value in fields.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        self._dirty = True
        return True

    def remove_entry(self, canonical_url: str) -> Optional[ManifestEntry]:
        """Remove and return an entry. Returns None if not found."""
        entry = self._entries.pop(canonical_url, None)
        if entry:
            self._dirty = True
        return entry

    def mark_archived(self, canonical_url: str) -> bool:
        """Transition a URL to archived status."""
        return self.update_entry(
            canonical_url,
            status="archived",
            last_crawl_time=datetime.now(IST).isoformat(),
        )

    def mark_error(self, canonical_url: str, error_message: str) -> bool:
        """Mark a URL as having encountered an error."""
        return self.update_entry(
            canonical_url,
            status="error",
            error_message=error_message,
            last_crawl_time=datetime.now(IST).isoformat(),
        )

    # ── Query Methods ────────────────────────────────

    def get_all_entries(self) -> Dict[str, ManifestEntry]:
        """Return all entries (defensive copy)."""
        return dict(self._entries)

    def get_all_canonical_urls(self) -> Set[str]:
        """Return set of all canonical URLs in the manifest."""
        return set(self._entries.keys())

    def get_active_urls(self) -> Set[str]:
        """Return canonical URLs with active status."""
        return {
            url for url, entry in self._entries.items()
            if entry.status == "active"
        }

    def get_urls_by_status(self, status: str) -> List[ManifestEntry]:
        """Filter entries by status (active, archived, error)."""
        return [
            entry for entry in self._entries.values()
            if entry.status == status
        ]

    def get_stale_urls(self, max_age_hours: float = 168.0) -> List[ManifestEntry]:
        """Find URLs that haven't been crawled within the threshold."""
        cutoff = datetime.now(IST) - timedelta(hours=max_age_hours)
        stale = []
        for entry in self._entries.values():
            if entry.status != "active":
                continue
            if not entry.last_crawl_time:
                stale.append(entry)
                continue
            try:
                last_crawl = datetime.fromisoformat(entry.last_crawl_time)
                if last_crawl < cutoff:
                    stale.append(entry)
            except (ValueError, TypeError):
                stale.append(entry)
        return stale

    def get_chunk_ids_for_url(self, canonical_url: str) -> List[str]:
        """Return chunk IDs associated with a URL."""
        entry = self._entries.get(canonical_url)
        if entry:
            return list(entry.chunk_ids)
        return []

    def get_all_chunk_ids(self) -> Set[str]:
        """Return all chunk IDs across all active entries."""
        ids = set()
        for entry in self._entries.values():
            if entry.status == "active":
                ids.update(entry.chunk_ids)
        return ids

    # ── Metadata Operations ──────────────────────────

    def update_sync_metadata(self, run_id: str) -> None:
        """Update manifest metadata after a sync run."""
        self._metadata["last_sync_time"] = datetime.now(IST).isoformat()
        self._metadata["last_sync_run_id"] = run_id
        self._metadata["total_syncs"] = self._metadata.get("total_syncs", 0) + 1
        self._dirty = True

    def get_metadata(self) -> Dict[str, Any]:
        """Return manifest metadata."""
        return deepcopy(self._metadata)

    # ── Statistics ────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return summary statistics about the manifest."""
        status_counts = {"active": 0, "archived": 0, "error": 0}
        total_chunks = 0
        categories = set()
        collections = set()

        for entry in self._entries.values():
            status_counts[entry.status] = status_counts.get(entry.status, 0) + 1
            total_chunks += len(entry.chunk_ids)
            if entry.category:
                categories.add(entry.category)
            if entry.collection:
                collections.add(entry.collection)

        return {
            "total_entries": len(self._entries),
            "active": status_counts.get("active", 0),
            "archived": status_counts.get("archived", 0),
            "error": status_counts.get("error", 0),
            "total_chunks_tracked": total_chunks,
            "categories": sorted(categories),
            "collections": sorted(collections),
            "total_syncs": self._metadata.get("total_syncs", 0),
            "last_sync_time": self._metadata.get("last_sync_time", ""),
        }

    @property
    def entry_count(self) -> int:
        """Number of entries in the manifest."""
        return len(self._entries)

    @property
    def is_empty(self) -> bool:
        """Whether the manifest has any entries."""
        return len(self._entries) == 0

    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"SyncManifest(entries={stats['total_entries']}, "
            f"active={stats['active']}, archived={stats['archived']}, "
            f"error={stats['error']})"
        )
