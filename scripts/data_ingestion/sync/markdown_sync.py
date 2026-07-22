#!/usr/bin/env python3
"""
markdown_sync.py

Markdown file lifecycle manager for the knowledge sync pipeline.
Handles creation, update, and archival/deletion of markdown files
based on change detection results.
"""

import logging
import os
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict

from scripts.data_ingestion.sync.manifest import SyncManifest, ManifestEntry
from scripts.data_ingestion.sync import SYNC_SYSTEM_VERSION

logger = logging.getLogger("sync.markdown_sync")

IST = timezone(timedelta(hours=5, minutes=30))


class MarkdownSyncManager:
    """
    Manages the markdown file lifecycle during knowledge sync.

    - Creates new markdown files for NEW pages.
    - Updates existing markdown files for MODIFIED pages.
    - Archives or deletes markdown files for DELETED pages.
    - Enriches frontmatter with extended sync metadata.
    """

    def __init__(
        self,
        manifest: SyncManifest,
        config: Dict[str, Any],
        sync_run_id: str = "",
    ):
        self.manifest = manifest
        self.config = config
        self.sync_run_id = sync_run_id

        ingestion_cfg = config.get("ingestion", {})
        sync_cfg = config.get("sync", {})
        versioning_cfg = config.get("versioning", {})

        self.knowledge_dir = Path(ingestion_cfg.get("knowledge_dir", "knowledge_new"))
        self.archive_deleted = sync_cfg.get("archive_deleted", True)
        self.archive_dir = Path(sync_cfg.get("archive_dir", "knowledge_new/_archived"))
        self.scraper_version = versioning_cfg.get("scraper_version", SYNC_SYSTEM_VERSION)

        # Statistics
        self.stats = {
            "created": 0,
            "updated": 0,
            "archived": 0,
            "deleted": 0,
            "errors": 0,
        }

    def process_new_page(
        self,
        canonical_url: str,
        title: str,
        category: str,
        content_hash: str,
        markdown_path: str,
    ) -> bool:
        """
        Register a newly created markdown file in the manifest.
        (The actual file writing is done by the crawler using write_markdown_file.)

        Returns True on success.
        """
        if not markdown_path or not os.path.exists(markdown_path):
            logger.warning(f"Markdown file not found for NEW page: {canonical_url}")
            return False

        now = datetime.now(IST).isoformat()

        entry = ManifestEntry(
            url=canonical_url,
            canonical_url=canonical_url,
            last_crawl_time=now,
            content_hash=content_hash,
            markdown_path=str(Path(markdown_path).as_posix()),
            markdown_hash=self._compute_file_hash(markdown_path),
            category=category,
            collection="",  # Will be set by embedding_updater
            status="active",
            http_status=200,
            title=title,
            scraper_version=self.scraper_version,
            crawl_count=1,
            first_seen=now,
        )
        self.manifest.set_entry(entry)
        self.stats["created"] += 1
        logger.info(f"NEW markdown registered: {markdown_path}")
        return True

    def process_modified_page(
        self,
        canonical_url: str,
        title: str,
        category: str,
        content_hash: str,
        markdown_path: str,
    ) -> bool:
        """
        Update the manifest entry for a modified page.
        The markdown file has already been overwritten by the crawler.

        Returns True on success.
        """
        existing = self.manifest.get_entry(canonical_url)
        if not existing:
            # Treat as new if not found
            return self.process_new_page(
                canonical_url, title, category, content_hash, markdown_path
            )

        now = datetime.now(IST).isoformat()

        self.manifest.update_entry(
            canonical_url,
            last_crawl_time=now,
            content_hash=content_hash,
            markdown_path=str(Path(markdown_path).as_posix()) if markdown_path else existing.markdown_path,
            markdown_hash=self._compute_file_hash(markdown_path) if markdown_path else existing.markdown_hash,
            category=category or existing.category,
            title=title or existing.title,
            http_status=200,
            status="active",
            error_message="",
            scraper_version=self.scraper_version,
            crawl_count=existing.crawl_count + 1,
            # chunk_ids will be cleared and re-populated by embedding_updater
        )

        self.stats["updated"] += 1
        logger.info(f"MODIFIED markdown updated: {canonical_url}")
        return True

    def process_deleted_page(self, canonical_url: str) -> bool:
        """
        Handle a deleted page by archiving or deleting its markdown file
        and updating the manifest.

        Returns True on success.
        """
        entry = self.manifest.get_entry(canonical_url)
        if not entry:
            logger.warning(f"No manifest entry for deleted URL: {canonical_url}")
            return False

        # Archive or delete the markdown file
        if entry.markdown_path:
            md_path = Path(entry.markdown_path)
            if md_path.exists():
                if self.archive_deleted:
                    success = self._archive_file(md_path, entry)
                    if success:
                        self.stats["archived"] += 1
                    else:
                        self.stats["errors"] += 1
                        return False
                else:
                    try:
                        md_path.unlink()
                        self.stats["deleted"] += 1
                        logger.info(f"DELETED markdown: {md_path}")
                    except Exception as e:
                        logger.error(f"Failed to delete {md_path}: {e}")
                        self.stats["errors"] += 1
                        return False

        # Mark as archived in manifest
        self.manifest.mark_archived(canonical_url)
        return True

    def process_unchanged_page(self, canonical_url: str) -> None:
        """
        Update the last_crawl_time for an unchanged page without
        modifying the markdown file or vectors.
        """
        now = datetime.now(IST).isoformat()
        self.manifest.update_entry(
            canonical_url,
            last_crawl_time=now,
            http_status=200,
            status="active",
            error_message="",
        )

    def process_error_page(self, canonical_url: str, error_message: str) -> None:
        """Mark a page as having an error in the manifest."""
        self.manifest.mark_error(canonical_url, error_message)
        self.stats["errors"] += 1

    def _archive_file(self, file_path: Path, entry: ManifestEntry) -> bool:
        """Move a markdown file to the archive directory."""
        try:
            self.archive_dir.mkdir(parents=True, exist_ok=True)

            # Use category subfolder in archive
            archive_category_dir = self.archive_dir / (entry.category or "general")
            archive_category_dir.mkdir(parents=True, exist_ok=True)

            # Add timestamp to filename to avoid collisions
            timestamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
            archived_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
            dest = archive_category_dir / archived_name

            shutil.move(str(file_path), str(dest))
            logger.info(f"ARCHIVED: {file_path} -> {dest}")
            return True

        except Exception as e:
            logger.error(f"Failed to archive {file_path}: {e}")
            return False

    def _compute_file_hash(self, file_path: str) -> str:
        """Compute SHA-256 hash of a file's contents."""
        import hashlib
        try:
            with open(file_path, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            return f"sha256:{file_hash}"
        except Exception:
            return ""

    def get_stats(self) -> Dict[str, int]:
        """Return sync statistics."""
        return dict(self.stats)
