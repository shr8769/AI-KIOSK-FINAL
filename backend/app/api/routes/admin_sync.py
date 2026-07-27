"""
Admin Sync API Routes — /api/v1/admin/sync/*

Provides REST endpoints for:
- Sync Dashboard (combined status + stats)
- Live Monitor (HTTP polling fallback for sync progress)
- Sync Trigger (manual sync with mode selection)
- Schedule Management (set/get sync interval)
- Analytics (detailed knowledge base stats)
"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.sync_state_manager import SyncStateManager

logger = logging.getLogger(__name__)
router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Response Models ──────────────────────────────────────────

class DashboardResponse(BaseModel):
    last_sync_time: str = "Never"
    sync_status: str = "idle"
    is_syncing: bool = False
    total_pages: int = 0
    total_chunks: int = 0
    total_embeddings: int = 0
    failed_pages: int = 0
    duplicate_pages: int = 0
    total_syncs: int = 0
    statuses: Dict[str, int] = {}
    collections: Dict[str, int] = {}
    categories: Dict[str, int] = {}
    schedule: Dict[str, Any] = {}


class ProgressResponse(BaseModel):
    is_syncing: bool = False
    status: str = "idle"
    stage: str = ""
    stage_number: int = 0
    total_stages: int = 7
    current_url: str = ""
    pages_total: int = 0
    pages_done: int = 0
    pages_remaining: int = 0
    pages_failed: int = 0
    progress_pct: float = 0.0
    errors: List[str] = []
    warnings: List[str] = []
    started_at: str = ""
    updated_at: str = ""


class SyncTriggerRequest(BaseModel):
    mode: str = "incremental"  # incremental | full
    max_pages: Optional[int] = None
    dry_run: bool = False


class SyncTriggerResponse(BaseModel):
    status: str
    message: str
    summary: Dict[str, Any] = {}


class ScheduleRequest(BaseModel):
    interval: str  # 5min | 15min | 1hour | daily
    auto_sync_enabled: Optional[bool] = None


class ScheduleResponse(BaseModel):
    success: bool = True
    interval: str = "daily"
    interval_seconds: int = 86400
    auto_sync_enabled: bool = True
    valid_intervals: List[str] = []
    message: str = ""


class AnalyticsResponse(BaseModel):
    total_pages: int = 0
    total_chunks: int = 0
    total_embeddings: int = 0
    duplicate_pages: int = 0
    failed_pages: int = 0
    statuses: Dict[str, int] = {}
    collections: Dict[str, int] = {}
    categories: Dict[str, int] = {}
    total_syncs: int = 0
    last_sync_time: str = ""
    last_sync_run_id: str = ""
    most_frequently_updated: List[Dict[str, Any]] = []


# ── Dashboard Route ──────────────────────────────────────────

@router.get(
    "/admin/sync/dashboard",
    response_model=DashboardResponse,
    tags=["Admin Sync"],
)
async def get_dashboard():
    """
    Get combined dashboard data for the admin knowledge review screen.

    Returns last sync time, sync status, page/chunk/embedding counts,
    validation status, failure counts, and current schedule.
    """
    mgr = SyncStateManager()
    dashboard = mgr.get_dashboard()
    return DashboardResponse(**dashboard)


# ── Live Monitor Route (HTTP fallback) ───────────────────────

@router.get(
    "/admin/sync/progress",
    response_model=ProgressResponse,
    tags=["Admin Sync"],
)
async def get_sync_progress():
    """
    Get current sync progress.

    This is the HTTP polling fallback for the WebSocket-based live monitor.
    Returns the current stage, URL being crawled, pages remaining,
    progress percentage, errors, and warnings.
    """
    mgr = SyncStateManager()
    progress = mgr.get_progress()
    return ProgressResponse(**progress)


# ── Sync Trigger Route ───────────────────────────────────────

@router.post(
    "/admin/sync/trigger",
    response_model=SyncTriggerResponse,
    tags=["Admin Sync"],
)
async def trigger_sync(request: SyncTriggerRequest):
    """
    Manually trigger a knowledge synchronization.

    Supports incremental (default) or full mode. Optionally limit
    the number of pages to crawl and enable dry-run mode.
    """
    mgr = SyncStateManager()

    if mgr.is_syncing:
        return SyncTriggerResponse(
            status="skipped",
            message="Sync already in progress",
        )

    try:
        from agents.autonomous.base_autonomous_agent import load_agent_config
        from agents.autonomous.knowledge_sync_agent import KnowledgeSyncAgent

        config = load_agent_config()

        # Apply overrides from request
        if request.max_pages:
            config.setdefault("knowledge_sync", {})["max_pages_override"] = request.max_pages
        if request.dry_run:
            config.setdefault("knowledge_sync", {})["dry_run"] = True

        agent = KnowledgeSyncAgent(config)

        # Update progress tracking
        mgr.start_sync_progress()

        # Run sync in background thread to avoid blocking
        import threading

        def run_sync_background():
            try:
                result = agent.trigger_manual_sync()
                if result:
                    mgr.finish_sync_progress(result.success)
                else:
                    mgr.finish_sync_progress(False)
            except Exception as e:
                logger.error(f"Background sync failed: {e}", exc_info=True)
                mgr.finish_sync_progress(False)

        thread = threading.Thread(target=run_sync_background, daemon=True)
        thread.start()

        return SyncTriggerResponse(
            status="started",
            message=f"Knowledge sync started in {request.mode} mode",
            summary={"mode": request.mode, "dry_run": request.dry_run},
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Agent configuration not found. Create agent_config.yaml.",
        )
    except Exception as e:
        logger.error(f"Failed to trigger sync: {e}", exc_info=True)
        mgr.finish_sync_progress(False)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger sync: {str(e)}",
        )


# ── Schedule Routes ──────────────────────────────────────────

@router.get(
    "/admin/sync/schedule",
    response_model=ScheduleResponse,
    tags=["Admin Sync"],
)
async def get_schedule():
    """
    Get the current sync schedule configuration.

    Returns the active interval, whether auto-sync is enabled,
    and the list of valid interval options.
    """
    mgr = SyncStateManager()
    schedule = mgr.get_schedule()
    return ScheduleResponse(**schedule)


@router.put(
    "/admin/sync/schedule",
    response_model=ScheduleResponse,
    tags=["Admin Sync"],
)
async def set_schedule(request: ScheduleRequest):
    """
    Update the sync schedule.

    Valid intervals: 5min, 15min, 1hour, daily.
    The new schedule takes effect on the next sync cycle.
    """
    mgr = SyncStateManager()
    result = mgr.set_schedule(
        interval=request.interval,
        auto_sync_enabled=request.auto_sync_enabled,
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return ScheduleResponse(**result, valid_intervals=list(mgr.get_schedule()["valid_intervals"]))


# ── Analytics Route ──────────────────────────────────────────

@router.get(
    "/admin/analytics",
    response_model=AnalyticsResponse,
    tags=["Admin Analytics"],
)
async def get_analytics():
    """
    Get detailed knowledge base analytics.

    Returns total pages, chunks, embeddings, duplicates, failures,
    average sync time, collection/category breakdowns, and the
    most frequently updated pages.
    """
    mgr = SyncStateManager()
    analytics = mgr.get_analytics()
    return AnalyticsResponse(**analytics)
