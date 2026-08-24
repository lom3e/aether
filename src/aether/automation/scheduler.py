"""
AutomationScheduler — Background asynchronous scheduler for Aether automations.
Evaluates triggers (cron, interval, file watchers) and dispatches workflow execution.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from aether.automation.engine import AutomationEngine
from aether.automation.models import AutomationDefinition, AutomationRunRecord, TriggerType
from aether.automation.triggers import TriggerEvaluator

logger = logging.getLogger(__name__)


class AutomationScheduler:
    """Manages the background evaluation loop and job execution for Workspace automations."""

    def __init__(
        self,
        workspace: Any,
        event_bus: Any = None,
        tick_interval_seconds: float = 5.0,
        max_concurrent_runs: int = 3,
    ) -> None:
        self.workspace = workspace
        self.event_bus = event_bus
        self.tick_interval = tick_interval_seconds
        self.max_concurrent_runs = max_concurrent_runs

        self.engine = AutomationEngine(workspace=workspace, event_bus=event_bus)
        self._running_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._active_runs: set[str] = set()  # Set of automation IDs currently running
        self._last_file_check: datetime = datetime.now(timezone.utc)

    @property
    def is_running(self) -> bool:
        return self._running_task is not None and not self._running_task.done()

    def start(self) -> None:
        """Starts the background scheduler loop."""
        if self.is_running:
            return
        self._stop_event.clear()
        self._running_task = asyncio.create_task(self._loop(), name="aether-automation-scheduler")
        logger.info("AutomationScheduler started with tick interval %.1fs", self.tick_interval)

    async def stop(self) -> None:
        """Gracefully stops the scheduler loop."""
        if not self.is_running:
            return
        self._stop_event.set()
        if self._running_task:
            self._running_task.cancel()
            try:
                await self._running_task
            except (asyncio.CancelledError, Exception):
                pass
            self._running_task = None
        logger.info("AutomationScheduler stopped")

    async def _loop(self) -> None:
        """Main evaluation loop."""
        while not self._stop_event.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in AutomationScheduler tick: %s", exc)

            try:
                await asyncio.sleep(self.tick_interval)
            except asyncio.CancelledError:
                break

    async def tick(self) -> list[AutomationRunRecord]:
        """Runs a single evaluation pass over all enabled automations. Returns triggered run records."""
        if not hasattr(self.workspace, "automations"):
            return []

        automations = self.workspace.automations.list_automations()
        now = datetime.now(timezone.utc)
        triggered_runs: list[AutomationRunRecord] = []

        for auto in automations:
            if not auto.enabled:
                continue

            # Prevent overlapping runs for the same automation
            if auto.id in self._active_runs:
                continue

            # Concurrency limit check
            if len(self._active_runs) >= self.max_concurrent_runs:
                break

            # Parse last run datetime
            last_run_dt: datetime | None = None
            if auto.last_run_at:
                try:
                    last_run_dt = datetime.fromisoformat(auto.last_run_at)
                except Exception:
                    pass

            is_due = False
            trigger_payload: dict[str, Any] = {}
            trigger_type_str = auto.trigger.type.value if hasattr(auto.trigger.type, "value") else str(auto.trigger.type)

            # 1. Schedule Trigger
            if auto.trigger.type == TriggerType.SCHEDULE:
                is_due, next_run = TriggerEvaluator.evaluate_schedule(auto.trigger, last_run_dt, now)
                if next_run:
                    auto.next_run_at = next_run.isoformat()
                    try:
                        self.workspace.automations.save_automation(auto)
                    except Exception:
                        pass

            # 2. File Watcher Trigger
            elif auto.trigger.type == TriggerType.FILE_WATCHER:
                is_due, detected_files = TriggerEvaluator.evaluate_file_watcher(
                    trigger=auto.trigger,
                    workspace_root=self.workspace.root,
                    last_check_at=self._last_file_check,
                )
                if is_due:
                    trigger_payload = {"detected_files": detected_files, "file_count": len(detected_files)}

            if is_due:
                # Launch execution in background task
                self._active_runs.add(auto.id)
                task = asyncio.create_task(
                    self._run_wrapper(auto, trigger_type_str, trigger_payload)
                )
                # For synchronous tick reporting
                # We also track it
                triggered_runs.append(
                    AutomationRunRecord(
                        automation_id=auto.id,
                        automation_name=auto.name,
                        trigger_type=trigger_type_str,
                    )
                )

        self._last_file_check = now
        return triggered_runs

    async def _run_wrapper(
        self,
        auto: AutomationDefinition,
        trigger_type: str,
        trigger_payload: dict[str, Any],
    ) -> AutomationRunRecord:
        try:
            return await self.engine.execute_automation(
                automation=auto,
                trigger_type=trigger_type,
                trigger_payload=trigger_payload,
            )
        finally:
            self._active_runs.discard(auto.id)

    async def trigger_now(
        self,
        automation_id: str,
        payload: dict[str, Any] | None = None,
    ) -> AutomationRunRecord | None:
        """Manually triggers an automation immediately."""
        auto = self.workspace.automations.get_automation(automation_id)
        if not auto:
            return None

        self._active_runs.add(auto.id)
        try:
            return await self.engine.execute_automation(
                automation=auto,
                trigger_type="manual",
                trigger_payload=payload or {},
            )
        finally:
            self._active_runs.discard(auto.id)
