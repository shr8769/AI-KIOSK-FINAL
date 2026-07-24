#!/usr/bin/env python3
"""
knowledge_sync_agent.py

Autonomous agent that wraps the existing sync_knowledge.py pipeline
to run it as a background service on a configurable schedule.

Does NOT duplicate any crawler, markdown, or embedding logic — it
simply orchestrates the existing pipeline and tracks results.
"""

import argparse
import logging
import sys
from datetime import timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.autonomous.base_autonomous_agent import (  # noqa: E402
    BaseAutonomousAgent,
    AgentRunResult,
)

logger = logging.getLogger("agent.knowledge_sync")

IST = timezone(timedelta(hours=5, minutes=30))


class KnowledgeSyncAgent(BaseAutonomousAgent):
    """
    Autonomous Knowledge Synchronization Agent.

    Wraps the existing sync_knowledge.run_sync() pipeline to monitor
    PES University websites and keep the knowledge base updated.

    Features:
        - Scheduled background execution (cron or interval)
        - Manual trigger via API
        - Non-overlapping sync protection
        - Sync history tracking
        - Delegates all actual work to the existing pipeline
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        ks_cfg = config.get("knowledge_sync", {})
        self._sync_config_path = ks_cfg.get("sync_config_path", "sync_config.yaml")
        self._max_history = ks_cfg.get("max_history", 30)
        self._on_startup_sync = ks_cfg.get("on_startup_sync", False)
        self._dry_run = ks_cfg.get("dry_run", False)
        self._max_pages_override = ks_cfg.get("max_pages_override")
        self._use_cron = ks_cfg.get("use_cron", True)
        self._cron_expr = ks_cfg.get("schedule_cron", "0 2 * * *")
        self._interval_hours = ks_cfg.get("schedule_interval_hours", 24)

        # Load the sync pipeline config
        self._sync_config: Optional[Dict[str, Any]] = None
        self._load_sync_config()

        # Progress tracking via admin state manager
        self._state_manager = None
        try:
            from backend.app.services.sync_state_manager import SyncStateManager
            self._state_manager = SyncStateManager()
        except ImportError:
            pass  # Admin dashboard not installed or not in path

    @property
    def agent_name(self) -> str:
        return "knowledge_sync"

    def _load_sync_config(self) -> None:
        """Load the sync pipeline configuration."""
        try:
            config_file = Path(self._sync_config_path)
            if config_file.exists():
                with open(config_file, "r", encoding="utf-8") as f:
                    self._sync_config = yaml.safe_load(f)
                self.logger.info(f"Loaded sync config from {config_file}")
            else:
                self.logger.warning(
                    f"Sync config not found at {config_file}. "
                    "Will use defaults from sync pipeline."
                )
        except Exception as e:
            self.logger.error(f"Error loading sync config: {e}")

    def get_interval_seconds(self) -> float:
        """Get the configured interval in seconds."""
        return self._interval_hours * 3600

    async def _execute_cycle(self) -> AgentRunResult:
        """
        Execute one knowledge synchronization cycle.

        Imports and calls the existing sync_knowledge.run_sync() function,
        passing the loaded configuration.
        """
        self.logger.info("=" * 60)
        self.logger.info("Knowledge Sync cycle starting...")
        self.logger.info("=" * 60)

        # Notify admin dashboard of sync start
        if self._state_manager:
            self._state_manager.start_sync_progress()

        try:
            # Import the existing sync pipeline
            from sync_knowledge import run_sync, load_config, setup_logging

            # Load fresh config each time (in case it was updated)
            sync_config = load_config(self._sync_config_path)

            # Apply overrides
            if self._max_pages_override:
                sync_config.setdefault("crawler", {})["max_pages"] = self._max_pages_override

            # Create a namespace matching what run_sync expects
            args = argparse.Namespace(
                dry_run=self._dry_run,
                full=False,
                max_pages=self._max_pages_override,
                config=self._sync_config_path,
                validate_only=False,
                schedule=False,
            )

            # Setup sync logging
            setup_logging(sync_config)

            # Run the existing pipeline
            summary = await run_sync(sync_config, args)

            # Build result
            change_summary = summary.get("change_summary", {})
            embedding_stats = summary.get("embedding_stats", {})

            report_summary = {
                "mode": summary.get("mode", "incremental"),
                "pages_scanned": change_summary.get("total_scanned", 0),
                "pages_new": change_summary.get("new", 0),
                "pages_modified": change_summary.get("modified", 0),
                "pages_deleted": change_summary.get("deleted", 0),
                "pages_unchanged": change_summary.get("unchanged", 0),
                "pages_errors": change_summary.get("errors", 0),
                "embeddings_created": embedding_stats.get("chunks_created", 0),
                "embeddings_deleted": embedding_stats.get("chunks_deleted", 0),
                "duration_seconds": summary.get("duration_seconds", 0),
                "report_path": summary.get("report_path", ""),
                "validation_passed": summary.get("validation", {}).get("all_passed", False),
            }

            success = change_summary.get("errors", 0) == 0
            self.logger.info(
                f"✅ Knowledge sync complete: "
                f"{report_summary['pages_scanned']} scanned, "
                f"{report_summary['pages_new']} new, "
                f"{report_summary['pages_modified']} modified, "
                f"{report_summary['pages_deleted']} deleted"
            )

            # Notify admin dashboard of completion
            if self._state_manager:
                self._state_manager.finish_sync_progress(success)

            return AgentRunResult(
                success=success,
                summary=report_summary,
            )

        except Exception as e:
            self.logger.error(f"Knowledge sync failed: {e}", exc_info=True)
            if self._state_manager:
                self._state_manager.finish_sync_progress(False)
            return AgentRunResult(
                success=False,
                summary={},
                error=str(e),
            )

    def start_scheduled(self) -> None:
        """Start the agent with configured schedule."""
        interval = self.get_interval_seconds()
        self.start(interval_seconds=interval)

        if self._on_startup_sync:
            self.logger.info("Running startup sync...")
            self.trigger_manual_sync()

    def get_sync_report(self) -> Dict[str, Any]:
        """Get the latest sync report for API consumption."""
        status = self.get_status()
        history = self.get_full_history()

        # Find the latest successful run
        latest_success = None
        for run in reversed(history):
            if run.get("success"):
                latest_success = run
                break

        return {
            **status,
            "sync_config_path": self._sync_config_path,
            "schedule": {
                "type": "cron" if self._use_cron else "interval",
                "cron": self._cron_expr if self._use_cron else None,
                "interval_hours": self._interval_hours if not self._use_cron else None,
            },
            "latest_successful_sync": latest_success,
            "full_history": history,
        }
