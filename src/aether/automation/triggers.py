"""
Trigger evaluation for Aether Automation Engine.
Supports Cron schedules, Interval timers, Filesystem Watchers, and Webhooks.
Zero external dependencies.
"""
from __future__ import annotations

import fnmatch
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from aether.automation.models import TriggerConfig, TriggerType


class CronExpression:
    """
    Evaluates standard 5-field cron expressions:
    `minute (0-59) hour (0-23) day-of-month (1-31) month (1-12) day-of-week (0-6, 0=Sunday)`
    Supports: `*`, `*/step`, `range (e.g. 1-5)`, `list (e.g. 1,15,30)`, and aliases (`@hourly`, `@daily`, etc.).
    """

    ALIASES = {
        "@yearly": "0 0 1 1 *",
        "@annually": "0 0 1 1 *",
        "@monthly": "0 0 1 * *",
        "@weekly": "0 0 * * 0",
        "@daily": "0 0 * * *",
        "@midnight": "0 0 * * *",
        "@hourly": "0 * * * *",
    }

    def __init__(self, expression: str):
        expr = expression.strip().lower()
        if expr in self.ALIASES:
            expr = self.ALIASES[expr]

        parts = expr.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: '{expression}'. Expected 5 fields.")

        self.expression = expr
        self.minutes = self._parse_field(parts[0], 0, 59)
        self.hours = self._parse_field(parts[1], 0, 23)
        self.days = self._parse_field(parts[2], 1, 31)
        self.months = self._parse_field(parts[3], 1, 12)
        self.weekdays = self._parse_field(parts[4], 0, 6)

    @staticmethod
    def _parse_field(field_str: str, min_val: int, max_val: int) -> set[int]:
        res: set[int] = set()
        for item in field_str.split(","):
            item = item.strip()
            if not item:
                continue
            if item == "*":
                res.update(range(min_val, max_val + 1))
            elif item.startswith("*/"):
                step = int(item[2:])
                res.update(range(min_val, max_val + 1, step))
            elif "-" in item:
                parts = item.split("-")
                start, end = int(parts[0]), int(parts[1])
                if "/" in str(end):
                    end_val, step = end.split("/")
                    res.update(range(start, int(end_val) + 1, int(step)))
                else:
                    res.update(range(start, int(end) + 1))
            else:
                val = int(item)
                # Day of week: 7 is also Sunday in standard cron
                if max_val == 6 and val == 7:
                    val = 0
                if min_val <= val <= max_val:
                    res.add(val)
        return res

    def matches(self, dt: datetime) -> bool:
        """Check if dt matches the cron expression."""
        # Convert weekday (Python: Monday=0, Sunday=6) -> Cron: Sunday=0, Monday=1, ..., Saturday=6
        cron_weekday = (dt.weekday() + 1) % 7

        return (
            dt.minute in self.minutes
            and dt.hour in self.hours
            and dt.day in self.days
            and dt.month in self.months
            and cron_weekday in self.weekdays
        )

    def next_run(self, from_dt: datetime | None = None) -> datetime:
        """Compute next matching datetime after from_dt (scans up to 365 days)."""
        dt = from_dt or datetime.now(timezone.utc)
        # Advance to start of next minute
        dt = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)

        limit_dt = dt + timedelta(days=366)
        while dt < limit_dt:
            cron_weekday = (dt.weekday() + 1) % 7
            if (
                dt.month in self.months
                and dt.day in self.days
                and cron_weekday in self.weekdays
                and dt.hour in self.hours
                and dt.minute in self.minutes
            ):
                return dt
            dt += timedelta(minutes=1)

        return dt


class TriggerEvaluator:
    """Evaluates various trigger types against current system state."""

    @classmethod
    def evaluate_schedule(
        cls,
        trigger: TriggerConfig,
        last_run_at: datetime | None,
        now: datetime | None = None,
    ) -> tuple[bool, datetime | None]:
        """
        Evaluates schedule triggers (cron or interval).
        Returns (is_due, next_run_dt).
        """
        curr = now or datetime.now(timezone.utc)

        # 1. Interval-based
        if trigger.interval_seconds and trigger.interval_seconds > 0:
            if last_run_at is None:
                # First run is due immediately
                next_run = curr + timedelta(seconds=trigger.interval_seconds)
                return True, next_run

            elapsed = (curr - last_run_at).total_seconds()
            is_due = elapsed >= trigger.interval_seconds
            next_run = last_run_at + timedelta(seconds=trigger.interval_seconds)
            if is_due:
                next_run = curr + timedelta(seconds=trigger.interval_seconds)
            return is_due, next_run

        # 2. Cron-based
        if trigger.cron:
            try:
                cron = CronExpression(trigger.cron)
                next_run = cron.next_run(last_run_at or (curr - timedelta(minutes=1)))
                is_due = curr >= next_run or cron.matches(curr)
                return is_due, next_run
            except Exception:
                return False, None

        return False, None

    @classmethod
    def evaluate_file_watcher(
        cls,
        trigger: TriggerConfig,
        workspace_root: Path,
        last_check_at: datetime,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """
        Checks if any files in watch_path matching watch_pattern were created or modified after last_check_at.
        """
        if not trigger.watch_path:
            target_dir = workspace_root
        else:
            rel = trigger.watch_path.lstrip("/")
            target_dir = (workspace_root / rel).resolve()

        if not target_dir.exists() or not target_dir.is_dir():
            return False, []

        pattern = trigger.watch_pattern or "*.*"
        detected_files: list[dict[str, Any]] = []

        try:
            for p in target_dir.rglob("*"):
                if p.is_file() and fnmatch.fnmatch(p.name, pattern):
                    # Ignore common noisy directories
                    if any(ignored in p.parts for ignored in [".git", "node_modules", ".venv", "__pycache__"]):
                        continue

                    stat = p.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                    ctime = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)

                    is_created = "created" in trigger.watch_events and ctime > last_check_at
                    is_modified = "modified" in trigger.watch_events and mtime > last_check_at

                    if is_created or is_modified:
                        detected_files.append({
                            "path": str(p),
                            "relative_path": str(p.relative_to(workspace_root)) if workspace_root in p.parents else p.name,
                            "size_bytes": stat.st_size,
                            "modified_at": mtime.isoformat(),
                            "event": "created" if is_created else "modified",
                        })
        except Exception:
            return False, []

        return len(detected_files) > 0, detected_files
