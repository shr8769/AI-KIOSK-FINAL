"""
announcement_service.py

Thin service wrapper around the existing AnnouncementStore that adds
unread filtering and bulk read operations for the admin dashboard.
"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.autonomous.announcement_store import AnnouncementStatus, AnnouncementStore  # noqa: E402

logger = logging.getLogger("admin.announcement_service")


class AnnouncementService:
    """
    Service layer for announcement operations.

    Wraps the existing AnnouncementStore and adds:
    - get_unread()  — announcements with status 'new'
    - mark_read()   — transition 'new' → 'active'
    - mark_all_read() — bulk transition
    """

    _instance: Optional["AnnouncementService"] = None

    @classmethod
    def get_instance(cls) -> "AnnouncementService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._store: Optional[AnnouncementStore] = None

    def _get_store(self) -> AnnouncementStore:
        """Lazy-load the announcement store with config."""
        if self._store is None:
            try:
                import yaml
                config_path = PROJECT_ROOT / "agent_config.yaml"
                if config_path.exists():
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = yaml.safe_load(f)
                    ann_cfg = config.get("announcements", {})
                    self._store = AnnouncementStore(
                        cache_path=ann_cfg.get("cache_path", "data/announcements.json"),
                        max_announcements=ann_cfg.get("max_announcements", 500),
                        expire_after_days=ann_cfg.get("expire_after_days", 90),
                        archive_after_days=ann_cfg.get("archive_after_days", 180),
                        new_badge_hours=ann_cfg.get("new_badge_hours", 48),
                    )
                else:
                    self._store = AnnouncementStore()
            except Exception as e:
                logger.error(f"Error initializing announcement store: {e}")
                self._store = AnnouncementStore()
        return self._store

    # ── Read Operations ──────────────────────────────────────

    def get_all_active(self) -> List[Dict[str, Any]]:
        """Get all active announcements (new + active)."""
        return self._get_store().get_active()

    def get_latest(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the latest N announcements."""
        return self._get_store().get_latest(limit=limit)

    def get_unread(self) -> List[Dict[str, Any]]:
        """Get only unread (status='new') announcements."""
        store = self._get_store()
        results = []
        for ann in store._announcements.values():
            if ann.status == AnnouncementStatus.NEW:
                d = ann.to_dict()
                d["is_new"] = True
                results.append(d)
        results.sort(key=lambda x: x["first_seen"], reverse=True)
        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get announcement statistics."""
        return self._get_store().get_stats()

    # ── Write Operations ─────────────────────────────────────

    def mark_read(self, announcement_id: str) -> bool:
        """Mark a single announcement as read (new → active)."""
        store = self._get_store()
        for ann in store._announcements.values():
            if ann.id == announcement_id and ann.status == AnnouncementStatus.NEW:
                ann.status = AnnouncementStatus.ACTIVE
                store.save()
                return True
        return False

    def mark_all_read(self) -> int:
        """Mark all 'new' announcements as 'active'. Returns count transitioned."""
        store = self._get_store()
        count = 0
        for ann in store._announcements.values():
            if ann.status == AnnouncementStatus.NEW:
                ann.status = AnnouncementStatus.ACTIVE
                count += 1
        if count > 0:
            store.save()
        return count
