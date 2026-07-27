"""
Knowledge Sync API Routes — GET/POST /api/v1/knowledge/sync/*

Provides REST endpoints for monitoring and triggering knowledge
base synchronization. Works with the KnowledgeSyncAgent.
"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Ensure project root is on path for agent imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Response Models ──────────────────────────────────────────

class SyncStatusResponse(BaseModel):
    agent_name: str = "knowledge_sync"
    status: str = "idle"
    is_running: bool = False
    last_run_time: Optional[str] = None
    next_run_time: Optional[str] = None
    consecutive_errors: int = 0
    total_runs: int = 0
    schedule: Optional[Dict[str, Any]] = None
    latest_successful_sync: Optional[Dict[str, Any]] = None
    recent_runs: List[Dict[str, Any]] = []


class SyncTriggerResponse(BaseModel):
    status: str
    message: str
    summary: Dict[str, Any] = {}


class SyncHistoryResponse(BaseModel):
    total_runs: int = 0
    runs: List[Dict[str, Any]] = []


# ── Routes ───────────────────────────────────────────────────

@router.get("/knowledge/sync/status", response_model=SyncStatusResponse, tags=["Knowledge Sync"])
async def get_sync_status():
    """
    Get current knowledge synchronization agent status.

    Returns the agent's running state, last/next sync times,
    error counts, and recent run history.
    """
    try:
        from agents.autonomous.base_autonomous_agent import load_agent_config
        from agents.autonomous.knowledge_sync_agent import KnowledgeSyncAgent

        config = load_agent_config()
        agent = KnowledgeSyncAgent(config)
        report = agent.get_sync_report()
        return SyncStatusResponse(**report)
    except FileNotFoundError:
        # Agent config not found — return default status
        return SyncStatusResponse()
    except Exception as e:
        logger.error(f"Error getting sync status: {e}", exc_info=True)
        return SyncStatusResponse(status="error")


@router.post("/knowledge/sync", response_model=SyncTriggerResponse, tags=["Knowledge Sync"])
async def trigger_knowledge_sync():
    """
    Trigger a manual knowledge synchronization.

    This loads the KnowledgeSyncAgent and runs one sync cycle.
    The sync is incremental by default — only changed pages are processed.
    """
    try:
        from agents.autonomous.base_autonomous_agent import load_agent_config
        from agents.autonomous.knowledge_sync_agent import KnowledgeSyncAgent

        config = load_agent_config()
        agent = KnowledgeSyncAgent(config)
        result = agent.trigger_manual_sync()

        if result is None:
            return SyncTriggerResponse(
                status="skipped",
                message="Knowledge sync already in progress",
            )

        return SyncTriggerResponse(
            status="success" if result.success else "error",
            message=(
                "Knowledge sync completed successfully"
                if result.success
                else f"Knowledge sync failed: {result.error}"
            ),
            summary=result.summary,
        )
    except Exception as e:
        logger.error(f"Manual knowledge sync failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Knowledge sync failed: {str(e)}",
        )


@router.get("/knowledge/sync/history", response_model=SyncHistoryResponse, tags=["Knowledge Sync"])
async def get_sync_history():
    """
    Get knowledge synchronization run history.

    Returns the full history of sync runs (up to the configured maximum).
    """
    try:
        from agents.autonomous.base_autonomous_agent import load_agent_config
        from agents.autonomous.knowledge_sync_agent import KnowledgeSyncAgent

        config = load_agent_config()
        agent = KnowledgeSyncAgent(config)
        history = agent.get_full_history()
        return SyncHistoryResponse(
            total_runs=len(history),
            runs=history,
        )
    except FileNotFoundError:
        return SyncHistoryResponse()
    except Exception as e:
        logger.error(f"Error getting sync history: {e}", exc_info=True)
        return SyncHistoryResponse()
