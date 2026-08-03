"""
Announcement API Routes — GET/POST /api/v1/announcements/*

Provides REST endpoints for fetching and syncing university announcements.
Works with the AnnouncementMonitorAgent's store.
"""

import logging
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

# Ensure project root is on path for agent imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.autonomous.announcement_store import AnnouncementStore  # noqa: E402

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Shared announcement store instance ───────────────────────
# Loaded lazily from the default cache path.
# The AnnouncementMonitorAgent writes to this same file.

_store: Optional[AnnouncementStore] = None


def _get_store() -> AnnouncementStore:
    """Get or initialize the shared announcement store."""
    global _store
    if _store is None:
        try:
            import yaml
            config_path = PROJECT_ROOT / "agent_config.yaml"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                ann_cfg = config.get("announcements", {})
                _store = AnnouncementStore(
                    cache_path=str(PROJECT_ROOT / ann_cfg.get("cache_path", "data/announcements.json")),
                    max_announcements=ann_cfg.get("max_announcements", 500),
                    expire_after_days=ann_cfg.get("expire_after_days", 90),
                    archive_after_days=ann_cfg.get("archive_after_days", 180),
                    new_badge_hours=ann_cfg.get("new_badge_hours", 48),
                )
            else:
                _store = AnnouncementStore(cache_path=str(PROJECT_ROOT / "data/announcements.json"))
        except Exception as e:
            logger.error(f"Error initializing announcement store: {e}")
            _store = AnnouncementStore(cache_path=str(PROJECT_ROOT / "data/announcements.json"))
    return _store


# ── Response Models ──────────────────────────────────────────

class AnnouncementItem(BaseModel):
    id: str
    title: str
    body: str
    posted_date: str = ""
    category: str = "General"
    source_url: str = ""
    status: str = "active"
    first_seen: str = ""
    last_seen: str = ""
    is_new: bool = False


class AnnouncementsResponse(BaseModel):
    announcements: List[AnnouncementItem]
    total: int


class SyncTriggerResponse(BaseModel):
    status: str
    message: str
    announcements_fetched: int = 0
    new: int = 0
    updated: int = 0


class AnnouncementStatsResponse(BaseModel):
    total: int
    by_status: dict = {}
    last_sync: str = ""
    total_syncs: int = 0


# ── Routes ───────────────────────────────────────────────────

@router.get("/announcements", response_model=AnnouncementsResponse, tags=["Announcements"])
async def get_announcements():
    """
    Get all active announcements.

    Returns announcements with status 'new' or 'active', sorted by
    newest first. Each announcement includes an `is_new` flag indicating
    whether it was first seen within the last 48 hours.
    """
    store = _get_store()
    store.load()
    active = store.get_active()
    return AnnouncementsResponse(
        announcements=[AnnouncementItem(**a) for a in active],
        total=len(active),
    )


@router.get("/announcements/latest", response_model=AnnouncementsResponse, tags=["Announcements"])
async def get_latest_announcements(
    limit: int = Query(default=10, ge=1, le=50, description="Maximum announcements to return"),
):
    """
    Get the latest N announcements.

    Returns the most recent active announcements up to the specified limit.
    """
    store = _get_store()
    print("DEBUG CACHE PATH:", store.cache_path)
    store.load()
    latest = store.get_latest(limit=limit)
    print("DEBUG ACTIVE:", len(latest))
    return AnnouncementsResponse(
        announcements=[AnnouncementItem(**a) for a in latest],
        total=len(latest),
    )


@router.get("/announcements/unread", response_model=AnnouncementsResponse, tags=["Announcements"])
async def get_unread_announcements():
    """
    Get only unread (status='new') announcements.

    Returns announcements that have not been marked as read yet,
    sorted by newest first. Each announcement has `is_new=True`.
    """
    from app.services.announcement_service import AnnouncementService
    service = AnnouncementService.get_instance()
    unread = service.get_unread()
    return AnnouncementsResponse(
        announcements=[AnnouncementItem(**a) for a in unread],
        total=len(unread),
    )


class MarkReadResponse(BaseModel):
    success: bool
    message: str
    count: int = 0


@router.post("/announcements/read/{announcement_id}", response_model=MarkReadResponse, tags=["Announcements"])
async def mark_announcement_read(announcement_id: str):
    """Mark a single announcement as read (new → active)."""
    from app.services.announcement_service import AnnouncementService
    service = AnnouncementService.get_instance()
    success = service.mark_read(announcement_id)
    return MarkReadResponse(
        success=success,
        message="Marked as read" if success else "Announcement not found or already read",
        count=1 if success else 0,
    )


@router.post("/announcements/read-all", response_model=MarkReadResponse, tags=["Announcements"])
async def mark_all_announcements_read():
    """Mark all unread announcements as read."""
    from app.services.announcement_service import AnnouncementService
    service = AnnouncementService.get_instance()
    count = service.mark_all_read()
    return MarkReadResponse(
        success=True,
        message=f"Marked {count} announcements as read",
        count=count,
    )


@router.get("/announcements/stats", response_model=AnnouncementStatsResponse, tags=["Announcements"])
async def get_announcement_stats():
    """Get announcement store statistics."""
    store = _get_store()
    stats = store.get_stats()
    return AnnouncementStatsResponse(**stats)


@router.post("/announcements/sync", response_model=SyncTriggerResponse, tags=["Announcements"])
async def trigger_announcement_sync():
    """
    Trigger a manual announcement synchronization.

    This loads the AnnouncementMonitorAgent and runs one sync cycle.
    If the agent is already running in the background, this triggers
    an additional immediate sync.
    """
    try:
        from agents.autonomous.announcement_monitor import AnnouncementMonitorAgent
        from agents.autonomous.base_autonomous_agent import load_agent_config

        config = load_agent_config()
        agent = AnnouncementMonitorAgent(config)
        result = agent.trigger_manual_sync()

        if result is None:
            return SyncTriggerResponse(
                status="skipped",
                message="Sync already in progress",
            )

        summary = result.summary
        return SyncTriggerResponse(
            status="success" if result.success else "error",
            message="Announcement sync completed" if result.success else f"Sync failed: {result.error}",
            announcements_fetched=summary.get("announcements_fetched", 0),
            new=summary.get("new", 0),
            updated=summary.get("updated", 0),
        )
    except Exception as e:
        logger.error(f"Manual announcement sync failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Announcement sync failed: {str(e)}",
        )
