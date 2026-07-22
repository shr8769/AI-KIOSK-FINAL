#!/usr/bin/env python3
"""
scheduler.py

Lightweight scheduling support for the knowledge sync pipeline.
Supports running sync as a periodic daemon using a cron-like schedule,
without requiring external dependencies.
"""

import logging
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

logger = logging.getLogger("sync.scheduler")

IST = timezone(timedelta(hours=5, minutes=30))


def parse_cron_expression(cron_expr: str) -> dict:
    """
    Parse a 5-field cron expression into a dictionary.
    Fields: minute hour day_of_month month day_of_week

    Supports: *, specific values, ranges (1-5), steps (*/5), lists (1,3,5)
    """
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        raise ValueError(f"Invalid cron expression: '{cron_expr}'. Expected 5 fields.")

    field_names = ["minute", "hour", "day_of_month", "month", "day_of_week"]
    field_ranges = {
        "minute": (0, 59),
        "hour": (0, 23),
        "day_of_month": (1, 31),
        "month": (1, 12),
        "day_of_week": (0, 6),  # 0=Sunday
    }

    parsed = {}
    for name, value, (low, high) in zip(field_names, fields, field_ranges.values()):
        parsed[name] = _expand_cron_field(value, low, high)

    return parsed


def _expand_cron_field(field: str, low: int, high: int) -> set:
    """Expand a single cron field into a set of valid integers."""
    values = set()

    for part in field.split(","):
        part = part.strip()

        # Wildcard with step: */5
        if part.startswith("*/"):
            step = int(part[2:])
            values.update(range(low, high + 1, step))
        # Plain wildcard: *
        elif part == "*":
            values.update(range(low, high + 1))
        # Range with step: 1-10/2
        elif "/" in part:
            range_part, step_part = part.split("/")
            step = int(step_part)
            if "-" in range_part:
                start, end = map(int, range_part.split("-"))
            else:
                start, end = low, high
            values.update(range(start, end + 1, step))
        # Range: 1-5
        elif "-" in part:
            start, end = map(int, part.split("-"))
            values.update(range(start, end + 1))
        # Single value
        else:
            values.add(int(part))

    return values


def matches_cron(cron_parsed: dict, dt: datetime) -> bool:
    """Check if a datetime matches a parsed cron schedule."""
    return (
        dt.minute in cron_parsed["minute"]
        and dt.hour in cron_parsed["hour"]
        and dt.day in cron_parsed["day_of_month"]
        and dt.month in cron_parsed["month"]
        and dt.weekday() in _convert_dow(cron_parsed["day_of_week"])
    )


def _convert_dow(cron_dow: set) -> set:
    """Convert cron day-of-week (0=Sunday) to Python weekday (0=Monday)."""
    python_dow = set()
    for d in cron_dow:
        if d == 0:
            python_dow.add(6)  # Sunday
        else:
            python_dow.add(d - 1)
    return python_dow


def next_cron_time(cron_parsed: dict, from_time: Optional[datetime] = None) -> datetime:
    """Calculate the next time a cron expression matches."""
    if from_time is None:
        from_time = datetime.now(IST)

    # Start from the next minute
    check = from_time.replace(second=0, microsecond=0) + timedelta(minutes=1)

    # Search up to 366 days ahead
    max_iterations = 366 * 24 * 60  # ~527,000 minutes
    for _ in range(max_iterations):
        if matches_cron(cron_parsed, check):
            return check
        check += timedelta(minutes=1)

    raise RuntimeError("Could not find next cron match within 366 days")


class SyncScheduler:
    """
    Runs the sync function on a cron-like schedule.

    Usage:
        scheduler = SyncScheduler(
            cron_expression="0 2 * * *",
            sync_function=my_sync_function,
        )
        scheduler.run()  # Blocks forever, runs sync at scheduled times
    """

    def __init__(
        self,
        cron_expression: str,
        sync_function: Callable,
        timezone_str: str = "Asia/Kolkata",
    ):
        self.cron_expression = cron_expression
        self.sync_function = sync_function
        self.timezone_str = timezone_str
        self._cron_parsed = parse_cron_expression(cron_expression)
        self._running = False

    def run(self) -> None:
        """
        Run the scheduler loop. Blocks indefinitely.
        Calls sync_function at each matching cron time.
        """
        self._running = True
        logger.info(f"Scheduler started with cron: '{self.cron_expression}'")

        while self._running:
            now = datetime.now(IST)
            next_run = next_cron_time(self._cron_parsed, now)
            wait_seconds = (next_run - now).total_seconds()

            logger.info(
                f"Next sync scheduled at: {next_run.strftime('%Y-%m-%d %H:%M IST')} "
                f"(in {wait_seconds / 3600:.1f} hours)"
            )

            # Sleep until next run (check every 30 seconds for stop signal)
            while wait_seconds > 0 and self._running:
                sleep_time = min(30, wait_seconds)
                time.sleep(sleep_time)
                wait_seconds -= sleep_time

            if not self._running:
                break

            # Execute sync
            logger.info("=" * 60)
            logger.info("Scheduled sync starting...")
            logger.info("=" * 60)

            try:
                self.sync_function()
                logger.info("Scheduled sync completed successfully.")
            except Exception as e:
                logger.error(f"Scheduled sync failed: {e}", exc_info=True)

    def stop(self) -> None:
        """Signal the scheduler to stop after the current cycle."""
        self._running = False
        logger.info("Scheduler stop requested.")
