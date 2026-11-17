#!/usr/bin/env python3
"""
run_agents.py

Top-level CLI entry point for launching autonomous agents.
Runs the KnowledgeSyncAgent and/or AnnouncementMonitorAgent
as background services with graceful shutdown support.

Usage:
    python run_agents.py                     # Run all agents
    python run_agents.py --knowledge-only    # Knowledge sync only
    python run_agents.py --announcements-only  # Announcements only
    python run_agents.py --status            # Show agent status
"""

import argparse
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Ensure UTF-8 output encoding for Windows CMD / PowerShell
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.autonomous.base_autonomous_agent import load_agent_config
from agents.autonomous.knowledge_sync_agent import KnowledgeSyncAgent
from agents.autonomous.announcement_monitor import AnnouncementMonitorAgent

IST = timezone(timedelta(hours=5, minutes=30))


def setup_root_logging(config: dict) -> None:
    """Configure root logging for the agent runner."""
    logging_cfg = config.get("logging", {})
    log_dir = Path(logging_cfg.get("log_dir", "logs/agents"))
    log_dir.mkdir(parents=True, exist_ok=True)

    log_level = getattr(
        logging, logging_cfg.get("log_level", "INFO").upper(), logging.INFO
    )

    formatter = logging.Formatter(
        "%(asctime)s [%(name)-28s] %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    if not root_logger.handlers:
        # Console
        console = logging.StreamHandler()
        console.setLevel(log_level)
        console.setFormatter(formatter)
        root_logger.addHandler(console)

        # File
        log_file = log_dir / "agent_runner.log"
        file_handler = logging.FileHandler(str(log_file), mode="a", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


logger = logging.getLogger("agent.runner")


def print_banner():
    """Print startup banner."""
    print()
    print("=" * 70)
    print("   VidyaSahayak AI-KIOSK — Autonomous Agent Runner")
    print("=" * 70)
    print(f"   Time       : {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}")
    print(f"   Python     : {sys.version.split()[0]}")
    print(f"   Project    : {PROJECT_ROOT}")
    print("=" * 70)
    print()


def run_agents(args: argparse.Namespace) -> None:
    """Start and manage autonomous agents."""
    config = load_agent_config(args.config)
    setup_root_logging(config)
    print_banner()

    agents = []
    runner_cfg = config.get("runner", {})
    shutdown_timeout = runner_cfg.get("graceful_shutdown_timeout_seconds", 30)

    # Initialize agents based on CLI flags
    ks_cfg = config.get("knowledge_sync", {})
    ann_cfg = config.get("announcements", {})

    if not args.announcements_only:
        if ks_cfg.get("enabled", True):
            ksa = KnowledgeSyncAgent(config)
            agents.append(ksa)
            logger.info(f"✅ KnowledgeSyncAgent initialized")
        else:
            logger.info("⏭ KnowledgeSyncAgent disabled in config")

    if not args.knowledge_only:
        if ann_cfg.get("enabled", True):
            ama = AnnouncementMonitorAgent(config)
            agents.append(ama)
            logger.info(f"✅ AnnouncementMonitorAgent initialized")
        else:
            logger.info("⏭ AnnouncementMonitorAgent disabled in config")

    if not agents:
        logger.warning("No agents enabled. Exiting.")
        print("\n   No agents enabled. Check agent_config.yaml.\n")
        return

    # Graceful shutdown handler
    shutdown_event = threading.Event()

    def signal_handler(signum, frame):
        logger.info("\n🛑 Shutdown signal received. Stopping agents...")
        shutdown_event.set()
        for agent in agents:
            agent.stop(timeout=shutdown_timeout)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start all agents
    print(f"   Starting {len(agents)} agent(s)...\n")
    for agent in agents:
        agent.start_scheduled()
        print(f"   [+] {agent.agent_name} — started")

    print()
    print("=" * 70)
    print("   All agents running. Press Ctrl+C to stop.")
    print("=" * 70)
    print()

    # Health check loop
    health_interval = runner_cfg.get("health_check_interval_seconds", 60)
    while not shutdown_event.is_set():
        shutdown_event.wait(timeout=health_interval)
        if not shutdown_event.is_set():
            for agent in agents:
                status = agent.get_status()
                logger.debug(
                    f"Health: {status['agent_name']} — "
                    f"status={status['status']}, "
                    f"runs={status['total_runs']}, "
                    f"errors={status['consecutive_errors']}"
                )

    print()
    print("=" * 70)
    print("   All agents stopped. Goodbye!")
    print("=" * 70)
    print()


def show_status(args: argparse.Namespace) -> None:
    """Display current status of all agents."""
    config = load_agent_config(args.config)

    print()
    print("=" * 70)
    print("   Agent Status Report")
    print("=" * 70)
    print()

    ks_cfg = config.get("knowledge_sync", {})
    ann_cfg = config.get("announcements", {})

    print("   [KNOWLEDGE] Knowledge Sync Agent")
    print(f"      Enabled     : {ks_cfg.get('enabled', True)}")
    print(f"      Schedule    : {ks_cfg.get('schedule_cron', '0 2 * * *')}")
    print(f"      Config      : {ks_cfg.get('sync_config_path', 'sync_config.yaml')}")
    print()

    print("   [ANNOUNCE] Announcement Monitor Agent")
    print(f"      Enabled     : {ann_cfg.get('enabled', True)}")
    print(f"      Interval    : {ann_cfg.get('check_interval_minutes', 30)} minutes")
    print(f"      Mock Data   : {ann_cfg.get('use_mock_data', True)}")
    print(f"      Target URL  : {ann_cfg.get('target_url', 'N/A')}")
    print()

    # Check announcement store
    try:
        from agents.autonomous.announcement_store import AnnouncementStore

        store = AnnouncementStore(
            cache_path=ann_cfg.get("cache_path", "data/announcements.json")
        )
        stats = store.get_stats()
        print(f"      Stored      : {stats['total']} announcements")
        print(f"      Last Sync   : {stats['last_sync'] or 'Never'}")
        print(f"      Total Syncs : {stats['total_syncs']}")
    except Exception:
        print("      Store       : Not initialized")

    print()
    print("=" * 70)
    print()


def main():
    parser = argparse.ArgumentParser(
        description="VidyaSahayak AI-KIOSK — Autonomous Agent Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all agents
  python run_agents.py

  # Run only knowledge sync agent
  python run_agents.py --knowledge-only

  # Run only announcement monitor
  python run_agents.py --announcements-only

  # Show agent status
  python run_agents.py --status

  # Use custom config
  python run_agents.py --config custom_agent_config.yaml
        """,
    )

    parser.add_argument(
        "--config", type=str, default="agent_config.yaml",
        help="Path to agent config YAML file (default: agent_config.yaml)",
    )
    parser.add_argument(
        "--knowledge-only", action="store_true",
        help="Run only the Knowledge Sync Agent",
    )
    parser.add_argument(
        "--announcements-only", action="store_true",
        help="Run only the Announcement Monitor Agent",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show current agent status and exit",
    )

    args = parser.parse_args()

    if args.status:
        show_status(args)
        return

    run_agents(args)


if __name__ == "__main__":
    main()
