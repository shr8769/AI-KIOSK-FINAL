#!/usr/bin/env python3
"""
base_autonomous_agent.py

Abstract base class for all autonomous agents in the AI-KIOSK.
Provides lifecycle management, scheduled execution, health tracking,
structured logging, error handling with retry logic, and status reporting.

Subclasses must implement:
    - agent_name (property)
    - _execute_cycle() — the core work for one run
"""

import abc
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

IST = timezone(timedelta(hours=5, minutes=30))


class AgentStatus(str, Enum):
    """Lifecycle states for an autonomous agent."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    COOLDOWN = "cooldown"


class AgentRunResult:
    """Result of a single agent execution cycle."""

    def __init__(
        self,
        success: bool,
        summary: Dict[str, Any],
        error: Optional[str] = None,
        duration_seconds: float = 0.0,
    ):
        self.success = success
        self.summary = summary
        self.error = error
        self.duration_seconds = duration_seconds
        self.timestamp = datetime.now(IST).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "summary": self.summary,
            "error": self.error,
            "duration_seconds": round(self.duration_seconds, 2),
            "timestamp": self.timestamp,
        }


class BaseAutonomousAgent(abc.ABC):
    """
    Abstract base class for autonomous background agents.

    Provides:
    - Configurable scheduled execution (interval-based or cron)
    - Thread-safe lifecycle management (start/stop/pause)
    - Automatic retry with exponential backoff
    - Run history tracking
    - Health status reporting
    - Structured logging to file and console
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._status = AgentStatus.IDLE
        self._running = False
        self._paused = False
        self._lock = threading.Lock()
        self._sync_lock = threading.Lock()  # Prevents overlapping executions
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Run history
        self._run_history: List[Dict[str, Any]] = []
        self._max_history = 30
        self._consecutive_errors = 0
        self._last_run_time: Optional[str] = None
        self._next_run_time: Optional[str] = None

        # Safety config
        safety_cfg = config.get("safety", {})
        self._max_consecutive_errors = safety_cfg.get("max_consecutive_errors", 5)
        self._error_cooldown_minutes = safety_cfg.get("error_cooldown_minutes", 15)

        # Retry config
        retry_cfg = config.get("retry", {})
        self._max_retries = retry_cfg.get("max_retries", 3)
        self._base_delay = retry_cfg.get("base_delay_seconds", 5)
        self._max_delay = retry_cfg.get("max_delay_seconds", 300)
        self._exponential_backoff = retry_cfg.get("exponential_backoff", True)
        self._jitter = retry_cfg.get("jitter", True)

        # Logging
        self._setup_logging(config.get("logging", {}))

    @property
    @abc.abstractmethod
    def agent_name(self) -> str:
        """Unique name for this agent (used in logging and status)."""
        ...

    @abc.abstractmethod
    async def _execute_cycle(self) -> AgentRunResult:
        """
        Execute one cycle of the agent's work.

        Must return an AgentRunResult with success/failure and summary.
        This method is called on schedule by the base class.
        """
        ...

    # ── Logging Setup ────────────────────────────────────────

    def _setup_logging(self, logging_cfg: Dict[str, Any]) -> None:
        """Configure agent-specific logger."""
        log_dir = Path(logging_cfg.get("log_dir", "logs/agents"))
        log_dir.mkdir(parents=True, exist_ok=True)
        log_level = getattr(
            logging, logging_cfg.get("log_level", "INFO").upper(), logging.INFO
        )

        self.logger = logging.getLogger(f"agent.{self.agent_name}")
        self.logger.setLevel(logging.DEBUG)

        # Avoid duplicate handlers on re-init
        if not self.logger.handlers:
            formatter = logging.Formatter(
                "%(asctime)s [%(name)-28s] %(levelname)-5s %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

            # Console handler
            if logging_cfg.get("console_output", True):
                console = logging.StreamHandler()
                console.setLevel(log_level)
                console.setFormatter(formatter)
                self.logger.addHandler(console)

            # File handler
            if logging_cfg.get("file_output", True):
                log_file = log_dir / f"{self.agent_name}.log"
                file_handler = logging.FileHandler(
                    str(log_file), mode="a", encoding="utf-8"
                )
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)

    # ── Lifecycle Management ─────────────────────────────────

    def start(self, interval_seconds: float = 3600) -> None:
        """
        Start the agent in a background thread.

        Args:
            interval_seconds: Time between execution cycles.
        """
        if self._running:
            self.logger.warning(f"{self.agent_name} is already running.")
            return

        self._running = True
        self._paused = False
        self._status = AgentStatus.RUNNING
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run_loop,
            args=(interval_seconds,),
            name=f"agent-{self.agent_name}",
            daemon=True,
        )
        self._thread.start()
        self.logger.info(
            f"🚀 {self.agent_name} started (interval: {interval_seconds}s)"
        )

    def stop(self, timeout: float = 30) -> None:
        """Stop the agent gracefully."""
        if not self._running:
            return

        self.logger.info(f"⏹ Stopping {self.agent_name}...")
        self._running = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        self._status = AgentStatus.STOPPED
        self.logger.info(f"✅ {self.agent_name} stopped.")

    def pause(self) -> None:
        """Pause the agent (skips execution cycles but keeps thread alive)."""
        self._paused = True
        self._status = AgentStatus.PAUSED
        self.logger.info(f"⏸ {self.agent_name} paused.")

    def resume(self) -> None:
        """Resume a paused agent."""
        self._paused = False
        self._status = AgentStatus.RUNNING
        self.logger.info(f"▶ {self.agent_name} resumed.")

    # ── Main Loop ────────────────────────────────────────────

    def _run_loop(self, interval_seconds: float) -> None:
        """Main execution loop running in a background thread."""
        import asyncio

        while self._running and not self._stop_event.is_set():
            if self._paused:
                self._stop_event.wait(timeout=5)
                continue

            # Check cooldown
            if self._status == AgentStatus.COOLDOWN:
                self.logger.info(
                    f"Agent in cooldown. Waiting {self._error_cooldown_minutes}m..."
                )
                self._stop_event.wait(timeout=self._error_cooldown_minutes * 60)
                self._status = AgentStatus.RUNNING
                self._consecutive_errors = 0
                continue

            # Execute cycle
            self._status = AgentStatus.RUNNING
            try:
                result = asyncio.run(self._execute_with_retry())
                self._record_run(result)

                if result.success:
                    self._consecutive_errors = 0
                else:
                    self._consecutive_errors += 1
                    if self._consecutive_errors >= self._max_consecutive_errors:
                        self.logger.error(
                            f"💀 {self._consecutive_errors} consecutive errors. "
                            f"Entering cooldown for {self._error_cooldown_minutes}m."
                        )
                        self._status = AgentStatus.COOLDOWN
                        continue

            except Exception as e:
                self.logger.error(
                    f"Unhandled error in {self.agent_name}: {e}",
                    exc_info=True,
                )
                self._consecutive_errors += 1
                self._record_run(
                    AgentRunResult(
                        success=False,
                        summary={},
                        error=str(e),
                    )
                )

            # Calculate next run time
            next_run = datetime.now(IST) + timedelta(seconds=interval_seconds)
            self._next_run_time = next_run.isoformat()

            # Wait for next cycle (interruptible)
            self._stop_event.wait(timeout=interval_seconds)

    async def _execute_with_retry(self) -> AgentRunResult:
        """Execute a cycle with retry logic."""
        import random

        last_error = None
        for attempt in range(1, self._max_retries + 1):
            try:
                start = time.time()
                result = await self._execute_cycle()
                result.duration_seconds = time.time() - start
                return result
            except Exception as e:
                last_error = e
                if attempt < self._max_retries:
                    delay = self._base_delay
                    if self._exponential_backoff:
                        delay = min(
                            self._base_delay * (2 ** (attempt - 1)),
                            self._max_delay,
                        )
                    if self._jitter:
                        delay += random.uniform(0, delay * 0.1)

                    self.logger.warning(
                        f"Attempt {attempt}/{self._max_retries} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await self._async_sleep(delay)
                else:
                    self.logger.error(
                        f"All {self._max_retries} attempts failed: {e}"
                    )

        return AgentRunResult(
            success=False,
            summary={"attempts": self._max_retries},
            error=f"All retries exhausted: {last_error}",
        )

    async def _async_sleep(self, seconds: float) -> None:
        """Async-compatible sleep."""
        import asyncio
        await asyncio.sleep(seconds)

    # ── Manual Trigger ───────────────────────────────────────

    def trigger_manual_sync(self) -> Optional[AgentRunResult]:
        """
        Manually trigger a single execution cycle.
        Returns the result, or None if already running.
        """
        if not self._sync_lock.acquire(blocking=False):
            self.logger.warning("Sync already in progress. Skipping manual trigger.")
            return None

        try:
            import asyncio
            self.logger.info(f"🔄 Manual sync triggered for {self.agent_name}")
            start = time.time()
            result = asyncio.run(self._execute_cycle())
            result.duration_seconds = time.time() - start
            self._record_run(result)
            return result
        except Exception as e:
            self.logger.error(f"Manual sync failed: {e}", exc_info=True)
            result = AgentRunResult(
                success=False, summary={}, error=str(e)
            )
            self._record_run(result)
            return result
        finally:
            self._sync_lock.release()

    # ── History & Status ─────────────────────────────────────

    def _record_run(self, result: AgentRunResult) -> None:
        """Record a run result to history."""
        self._last_run_time = result.timestamp
        self._run_history.append(result.to_dict())
        if len(self._run_history) > self._max_history:
            self._run_history = self._run_history[-self._max_history:]

    def get_status(self) -> Dict[str, Any]:
        """Get current agent status for API reporting."""
        return {
            "agent_name": self.agent_name,
            "status": self._status.value,
            "is_running": self._running,
            "is_paused": self._paused,
            "last_run_time": self._last_run_time,
            "next_run_time": self._next_run_time,
            "consecutive_errors": self._consecutive_errors,
            "total_runs": len(self._run_history),
            "recent_runs": self._run_history[-5:] if self._run_history else [],
        }

    def get_full_history(self) -> List[Dict[str, Any]]:
        """Get full run history."""
        return list(self._run_history)


def load_agent_config(config_path: str = "agent_config.yaml") -> Dict[str, Any]:
    """Load agent configuration from YAML file."""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(
            f"Agent config not found: {config_file.resolve()}. "
            f"Create agent_config.yaml from the template."
        )
    with open(config_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
