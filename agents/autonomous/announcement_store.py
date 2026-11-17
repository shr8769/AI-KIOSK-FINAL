#!/usr/bin/env python3
"""
announcement_store.py

JSON-based announcement persistence layer for the AnnouncementMonitorAgent.
Provides CRUD operations, deduplication, status lifecycle management,
and thread-safe file operations.

Announcement lifecycle: New → Active → Expired → Archived
"""

import hashlib
import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("agent.announcement_store")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

IST = timezone(timedelta(hours=5, minutes=30))


class AnnouncementStatus:
    """Announcement lifecycle states."""
    NEW = "new"
    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class Announcement:
    """Represents a single university announcement."""

    __slots__ = [
        "id", "title", "body", "posted_date", "category",
        "source_url", "content_hash", "status", "first_seen",
        "last_seen", "expire_at", "archive_at",
    ]

    def __init__(
        self,
        title: str,
        body: str,
        posted_date: str = "",
        category: str = "General",
        source_url: str = "",
        content_hash: str = "",
        status: str = AnnouncementStatus.NEW,
        first_seen: str = "",
        last_seen: str = "",
        id: str = "",
        expire_at: str = "",
        archive_at: str = "",
    ):
        now_iso = datetime.now(IST).isoformat()
        self.title = title
        self.body = body
        self.posted_date = posted_date
        self.category = category
        self.source_url = source_url
        self.content_hash = content_hash or self._compute_hash(title, body)
        self.status = status
        self.first_seen = first_seen or now_iso
        self.last_seen = last_seen or now_iso
        self.id = id or self.content_hash[:16]
        self.expire_at = expire_at
        self.archive_at = archive_at

    @staticmethod
    def _compute_hash(title: str, body: str = "") -> str:
        """Generate a stable SHA-256 hash from title for deduplication."""
        content = title.strip().lower()
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "posted_date": self.posted_date,
            "category": self.category,
            "source_url": self.source_url,
            "content_hash": self.content_hash,
            "status": self.status,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "expire_at": self.expire_at,
            "archive_at": self.archive_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Announcement":
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            body=data.get("body", ""),
            posted_date=data.get("posted_date", ""),
            category=data.get("category", "General"),
            source_url=data.get("source_url", ""),
            content_hash=data.get("content_hash", ""),
            status=data.get("status", AnnouncementStatus.NEW),
            first_seen=data.get("first_seen", ""),
            last_seen=data.get("last_seen", ""),
            expire_at=data.get("expire_at", ""),
            archive_at=data.get("archive_at", ""),
        )

    def is_new(self, new_badge_hours: int = 48) -> bool:
        """Check if this announcement qualifies for a 'New' badge."""
        try:
            first = datetime.fromisoformat(self.first_seen)
            cutoff = datetime.now(IST) - timedelta(hours=new_badge_hours)
            return first > cutoff
        except (ValueError, TypeError):
            return False


class AnnouncementStore:
    """
    Thread-safe JSON-based store for university announcements.

    Handles persistence, deduplication, lifecycle transitions,
    and provides query methods for the API layer.
    """

    def __init__(
        self,
        cache_path: str = "data/announcements.json",
        max_announcements: int = 500,
        expire_after_days: int = 90,
        archive_after_days: int = 180,
        new_badge_hours: int = 48,
    ):
        p = Path(cache_path)
        if not p.is_absolute():
            self.cache_path = (PROJECT_ROOT / p).resolve()
        else:
            self.cache_path = p.resolve()
        self.max_announcements = max_announcements
        self.expire_after_days = expire_after_days
        self.archive_after_days = archive_after_days
        self.new_badge_hours = new_badge_hours
        self._lock = threading.Lock()

        # In-memory store keyed by content_hash
        self._announcements: Dict[str, Announcement] = {}
        self._metadata: Dict[str, Any] = {
            "version": "1.0.0",
            "last_sync": "",
            "total_syncs": 0,
        }

        # Load existing data
        self.load()

    # ── Persistence ──────────────────────────────────────────

    def load(self) -> None:
        """Load announcements from JSON file."""
        if not self.cache_path.exists():
            logger.info(f"No existing announcement cache at {self.cache_path}")
            return

        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._metadata = data.get("metadata", self._metadata)
            entries = data.get("announcements", [])

            for entry in entries:
                ann = Announcement.from_dict(entry)
                self._announcements[ann.content_hash] = ann

            logger.info(
                f"Loaded {len(self._announcements)} announcements from {self.cache_path}"
            )
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading announcement cache: {e}")

    def save(self) -> None:
        """Persist announcements to JSON file with atomic write."""
        with self._lock:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "metadata": self._metadata,
                "announcements": [
                    ann.to_dict() for ann in self._announcements.values()
                ],
            }

            # Atomic write: write to temp file then rename
            try:
                fd, tmp_path = tempfile.mkstemp(
                    dir=str(self.cache_path.parent),
                    prefix=".announcements_",
                    suffix=".tmp",
                )
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                # On Windows, we need to remove target first
                if self.cache_path.exists():
                    self.cache_path.unlink()
                os.rename(tmp_path, str(self.cache_path))

                logger.debug(
                    f"Saved {len(self._announcements)} announcements to {self.cache_path}"
                )
            except Exception as e:
                logger.error(f"Error saving announcement cache: {e}")
                # Clean up temp file on failure
                try:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except OSError:
                    pass

    # ── CRUD Operations ──────────────────────────────────────

    def add_or_update(self, announcement: Announcement) -> bool:
        """
        Add a new announcement or update if it already exists.

        Returns True if the announcement was new, False if updated.
        """
        with self._lock:
            existing = self._announcements.get(announcement.content_hash)
            if existing:
                # Update last_seen and preserve first_seen
                existing.last_seen = datetime.now(IST).isoformat()
                # If newer scrape has longer body (e.g. details/PDF attachments loaded), update it
                if len(announcement.body) > len(existing.body):
                    existing.body = announcement.body
                if announcement.posted_date:
                    existing.posted_date = announcement.posted_date
                # Restore to active if it was previously expired or archived
                if existing.status in (AnnouncementStatus.EXPIRED, AnnouncementStatus.ARCHIVED):
                    existing.status = AnnouncementStatus.ACTIVE
                return False
            else:
                # Enforce max capacity
                if len(self._announcements) >= self.max_announcements:
                    self._evict_oldest()

                self._announcements[announcement.content_hash] = announcement
                return True

    def remove(self, content_hash: str) -> bool:
        """Remove an announcement by content hash."""
        with self._lock:
            if content_hash in self._announcements:
                del self._announcements[content_hash]
                return True
            return False

    def mark_deleted(self, content_hash: str) -> None:
        """Mark an announcement as archived (soft delete)."""
        with self._lock:
            if content_hash in self._announcements:
                self._announcements[content_hash].status = AnnouncementStatus.ARCHIVED

    def _evict_oldest(self) -> None:
        """Remove the oldest archived/expired announcements to make space."""
        # Sort by first_seen, remove oldest archived first, then expired
        archived = [
            (h, a) for h, a in self._announcements.items()
            if a.status == AnnouncementStatus.ARCHIVED
        ]
        archived.sort(key=lambda x: x[1].first_seen)

        if archived:
            del self._announcements[archived[0][0]]
            return

        expired = [
            (h, a) for h, a in self._announcements.items()
            if a.status == AnnouncementStatus.EXPIRED
        ]
        expired.sort(key=lambda x: x[1].first_seen)

        if expired:
            del self._announcements[expired[0][0]]

    # ── Lifecycle Management ─────────────────────────────────

    def update_lifecycle(self) -> Dict[str, int]:
        """
        Transition announcements through lifecycle stages based on age.
        Returns counts of transitions made.
        """
        now = datetime.now(IST)
        transitions = {"new_to_active": 0, "active_to_expired": 0, "expired_to_archived": 0}

        with self._lock:
            for ann in self._announcements.values():
                try:
                    parsed_posted = self._parse_date(ann.posted_date)
                    if parsed_posted:
                        dt = datetime.fromisoformat(parsed_posted)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=IST)
                        age_days = (now - dt).days
                    else:
                        first_seen = datetime.fromisoformat(ann.first_seen)
                        age_days = (now - first_seen).days

                    # If announcement is recent, ensure it is active
                    if age_days <= self.expire_after_days and ann.status in (AnnouncementStatus.EXPIRED, AnnouncementStatus.ARCHIVED):
                        ann.status = AnnouncementStatus.ACTIVE

                    if ann.status == AnnouncementStatus.NEW:
                        if age_days > (self.new_badge_hours / 24):
                            ann.status = AnnouncementStatus.ACTIVE
                            transitions["new_to_active"] += 1

                    elif ann.status == AnnouncementStatus.ACTIVE:
                        if age_days > self.expire_after_days:
                            ann.status = AnnouncementStatus.EXPIRED
                            transitions["active_to_expired"] += 1

                    elif ann.status == AnnouncementStatus.EXPIRED:
                        if age_days > self.archive_after_days:
                            ann.status = AnnouncementStatus.ARCHIVED
                            transitions["expired_to_archived"] += 1

                except (ValueError, TypeError):
                    continue

        return transitions

    # ── Query Methods ────────────────────────────────────────

    def _parse_date(self, date_str: str) -> str:
        if not date_str:
            return ""
        try:
            import dateutil.parser
            cleaned = date_str.replace("Date:", "").strip()
            dt = dateutil.parser.parse(cleaned)
            return dt.isoformat()
        except Exception:
            return ""

    def get_active(self) -> List[Dict[str, Any]]:
        """Get all active (new + active) announcements, newest first."""
        results = []
        for ann in self._announcements.values():
            if ann.status in (AnnouncementStatus.NEW, AnnouncementStatus.ACTIVE):
                d = ann.to_dict()
                d["is_new"] = ann.is_new(self.new_badge_hours)
                results.append(d)
        
        def sort_key(x):
            return (self._parse_date(x.get("posted_date", "")), x.get("first_seen", ""))
            
        results.sort(key=sort_key, reverse=True)
        return results

    def get_latest(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the latest N active announcements."""
        active = self.get_active()
        return active[:limit]

    def get_all(self) -> List[Dict[str, Any]]:
        """Get all announcements regardless of status."""
        results = [ann.to_dict() for ann in self._announcements.values()]
        
        def sort_key(x):
            return (self._parse_date(x.get("posted_date", "")), x.get("first_seen", ""))
            
        results.sort(key=sort_key, reverse=True)
        return results

    def get_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get announcements filtered by status."""
        return [
            ann.to_dict()
            for ann in self._announcements.values()
            if ann.status == status
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Get announcement store statistics."""
        status_counts = {}
        for ann in self._announcements.values():
            status_counts[ann.status] = status_counts.get(ann.status, 0) + 1

        return {
            "total": len(self._announcements),
            "by_status": status_counts,
            "last_sync": self._metadata.get("last_sync", ""),
            "total_syncs": self._metadata.get("total_syncs", 0),
        }

    # ── Sync Metadata ────────────────────────────────────────

    def record_sync(self) -> None:
        """Record a sync event in metadata."""
        self._metadata["last_sync"] = datetime.now(IST).isoformat()
        self._metadata["total_syncs"] = self._metadata.get("total_syncs", 0) + 1
