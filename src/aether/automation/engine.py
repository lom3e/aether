"""
AutomationEngine — Executes multi-step agent pipelines and handles output destinations.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aether.automation.models import (
    AutomationDefinition,
    AutomationRunRecord,
    AutomationStatus,
    OutputType,
    PipelineStep,
    RunStatus,
    StepRunResult,
)
from aether.automation.triggers import TriggerEvaluator

logger = logging.getLogger(__name__)


def _is_error_retryable(error_str: str | None, retry_config: dict[str, Any] | None) -> bool:
    if not error_str:
        return False
    cfg = retry_config or {}
    retryable_patterns = cfg.get(
        "retryable_errors",
        ["timeout", "timed out", "502", "503", "504", "rate_limit", "429", "connection_error", "network error"],
    )
    lowered = error_str.lower()
    return any(p.lower() in lowered for p in retryable_patterns)


class AutomationEngine:
    """Executes automation workflows with DAG step dependencies, deduplication, retry, and truthful runtime state."""

    def __init__(self, workspace: Any, event_bus: Any = None, dedup_window_seconds: float = 3.0) -> None:
        self.workspace = workspace
        self.event_bus = event_bus
        self._recent_fingerprints: dict[str, float] = {}  # fingerprint -> timestamp
        self.dedup_window_seconds: float = dedup_window_seconds

    async def _execute_single_step(self, step: PipelineStep, prompt: str, team: Any) -> tuple[str, str, str | None]:
        """Executes a single step via team or canonical runtime. Returns (status, output, error)."""
        if team and hasattr(team, "run"):
            result = await asyncio.to_thread(team.run, prompt, target_agent=step.agent_name)
            step_output = result.output if hasattr(result, "output") else str(result)
            if hasattr(result, "success") and not result.success:
                return "failed", step_output, getattr(result, "error", "Step execution failed")
            return "completed", step_output, None

        if hasattr(self.workspace, "runtime") and self.workspace.runtime:
            from aether.core.execution import ExecutionMode, ExecutionStatus, Task
            runtime_task = Task(
                instruction=prompt,
                workspace_id=getattr(self.workspace, "id", "default"),
                agent_name=step.agent_name,
                mode=ExecutionMode.DELEGATE,
            )
            result = await asyncio.to_thread(self.workspace.runtime.execute, runtime_task)
            if result.status == ExecutionStatus.WAITING_FOR_APPROVAL:
                return "waiting_approval", result.output or "Action paused awaiting safety approval.", "Action requires safety approval."
            if result.success:
                return "completed", result.output or f"Executed step {step.name} successfully.", None
            return "failed", result.output or "", result.error or "Runtime execution failed"

        return "failed", "", f"No execution runtime or team available for step '{step.name}'"

    async def execute_automation(
        self,
        automation: AutomationDefinition,
        trigger_type: str = "manual",
        trigger_payload: dict[str, Any] | None = None,
        bypass_dedup: bool = False,
    ) -> AutomationRunRecord:
        start_time = time.time()
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        payload = trigger_payload or {}

        # 1. Deduplication / Idempotency Check
        fingerprint = TriggerEvaluator.compute_fingerprint(
            automation_id=automation.id,
            trigger_type=trigger_type,
            payload=payload,
        )

        curr_time = time.time()
        if not bypass_dedup:
            last_time = self._recent_fingerprints.get(fingerprint)
            if last_time and (curr_time - last_time < self.dedup_window_seconds):
                logger.info("Deduplication: suppressing repeat execution of automation '%s' (fingerprint: %s)", automation.id, fingerprint)
                # Check if we already recorded a run for this fingerprint in the store
                if hasattr(self.workspace, "automations"):
                    existing_run = self.workspace.automations.get_last_run_by_fingerprint(fingerprint)
                    if existing_run:
                        return existing_run
                return AutomationRunRecord(
                    automation_id=automation.id,
                    automation_name=automation.name,
                    trigger_type=trigger_type,
                    status=RunStatus.SUCCEEDED,
                    started_at=now_iso,
                    completed_at=now_iso,
                    output_result="Execution deduplicated within window",
                    trigger_fingerprint=fingerprint,
                )

        self._recent_fingerprints[fingerprint] = curr_time

        # Clean old fingerprints
        if len(self._recent_fingerprints) > 1000:
            cutoff = curr_time - 300
            self._recent_fingerprints = {k: v for k, v in self._recent_fingerprints.items() if v >= cutoff}

        run = AutomationRunRecord(
            automation_id=automation.id,
            automation_name=automation.name,
            trigger_type=trigger_type,
            status=RunStatus.RUNNING,
            started_at=now_iso,
            input_payload=payload,
            trigger_fingerprint=fingerprint,
        )

        # Update automation in-flight state
        automation.last_started_at = now_iso
        automation.runtime_status = AutomationStatus.RUNNING.value
        automation.last_fingerprint = fingerprint

        # Persist started run in store
        try:
            self.workspace.automations.record_run_started(run)
            self.workspace.automations.save_automation(automation)
        except Exception as exc:
            logger.warning("Failed to record automation run start: %s", exc)

        # Dispatch started event
        if self.event_bus:
            try:
                from aether.coordination.events import Event
                self.event_bus.publish(
                    Event(
                        type="automation:started",
                        source=f"automation:{automation.id}",
                        data={"run_id": run.run_id, "automation_name": automation.name, "trigger_type": trigger_type},
                    )
                )
            except Exception:
                pass

        step_results: list[dict[str, Any]] = []
        context_vars: dict[str, Any] = {
            "input": payload.get("input", payload.get("text", "")),
            "workspace_path": str(self.workspace.root),
            "workspace_name": getattr(self.workspace, "name", "Workspace"),
            **payload,
        }

        final_output: str = ""
        run_status = RunStatus.SUCCEEDED
        run_error: str | None = None
        total_retries = 0
        has_retryable_error = False

        # Load team
        team = None
        if hasattr(self.workspace, "load_team"):
            try:
                if automation.team_name:
                    team = self.workspace.load_team(automation.team_name)
                else:
                    team = self.workspace.load_team()
            except Exception:
                if hasattr(self.workspace, "teams_dir") and self.workspace.teams_dir.exists():
                    yaml_files = list(self.workspace.teams_dir.glob("*.yaml"))
                    if yaml_files:
                        try:
                            team = self.workspace.load_team(yaml_files[0].stem)
                        except Exception:
                            pass

        retry_cfg = automation.retry_config or {
            "max_retries": 3,
            "backoff_base": 2,
            "retryable_errors": ["timeout", "502", "503", "504", "rate_limit", "429", "connection_error"],
        }
        max_retries = int(retry_cfg.get("max_retries", 3))
        backoff_base = float(retry_cfg.get("backoff_base", 2))

        # If no steps defined, execute a single default step
        steps = automation.steps if automation.steps else [
            PipelineStep(
                id="step_default",
                name="Default Task",
                agent_name=team.manager.name if team and getattr(team, "manager", None) else "Manager",
                prompt_template="{input}" if payload else f"Execute automation task: {automation.name}",
            )
        ]

        for step in steps:
            step_start_time = time.time()
            step_start_iso = datetime.now(timezone.utc).isoformat()

            # Render prompt template
            prompt = step.prompt_template
            for k, v in context_vars.items():
                prompt = prompt.replace(f"{{{k}}}", str(v))

            step_output = ""
            step_err: str | None = None
            step_status = "completed"
            step_retries = 0

            for attempt in range(max_retries + 1):
                try:
                    step_status, step_output, step_err = await self._execute_single_step(step, prompt, team)
                except Exception as exc:
                    step_status = "failed"
                    step_output = ""
                    step_err = str(exc)
                    logger.error("Error executing step %s on attempt %d: %s", step.id, attempt, exc)


                # Check if retryable
                is_retryable = _is_error_retryable(step_err, retry_cfg)
                if step_status == "failed" and is_retryable and attempt < max_retries:
                    has_retryable_error = True
                    step_retries += 1
                    total_retries += 1
                    backoff = min(backoff_base ** attempt, 10.0)
                    logger.info("Retrying step '%s' (attempt %d/%d) after %.1fs backoff...", step.name, attempt + 1, max_retries, backoff)
                    await asyncio.sleep(backoff)
                else:
                    break

            step_duration = round(time.time() - step_start_time, 3)
            step_run = StepRunResult(
                step_id=step.id,
                step_name=step.name,
                agent_name=step.agent_name,
                status=step_status,
                prompt_used=prompt,
                output=step_output,
                error=step_err,
                started_at=step_start_iso,
                completed_at=datetime.now(timezone.utc).isoformat(),
                duration_seconds=step_duration,
            )
            step_results.append(step_run.to_dict())

            context_vars[f"{step.id}_output"] = step_output
            context_vars[f"step_{len(step_results)}_output"] = step_output
            final_output = step_output

            if step_status == "waiting_approval":
                run_status = RunStatus.WAITING_APPROVAL
                run_error = step_err
                break
            elif step_status == "failed":
                run_status = RunStatus.FAILED
                run_error = f"Step '{step.name}' failed: {step_err}"
                break

        # Output dispatching on success
        if run_status in (RunStatus.SUCCEEDED, RunStatus.COMPLETED) and automation.output_destination and final_output:
            out_dest = automation.output_destination
            try:
                if out_dest.type == OutputType.FILE and out_dest.target_path:
                    dest_file = (self.workspace.root / out_dest.target_path.lstrip("/")).resolve()
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    dest_file.write_text(final_output, encoding="utf-8")
                    logger.info("Saved automation output to %s", dest_file)

                elif out_dest.type == OutputType.KNOWLEDGE:
                    if hasattr(self.workspace, "knowledge"):
                        import hashlib
                        import uuid
                        from aether.knowledge.ingestion import DocumentIngester
                        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
                        filename = f"automation_{automation.id}_{int(time.time())}.md"
                        content_bytes = final_output.encode("utf-8")
                        content_hash = hashlib.sha256(content_bytes).hexdigest()
                        clean_scope = "project" if out_dest.project_id else "workspace"

                        self.workspace.knowledge.register_document(
                            doc_id=doc_id,
                            filename=filename,
                            size_bytes=len(content_bytes),
                            content_hash=content_hash,
                            scope=clean_scope,
                            project_id=out_dest.project_id,
                        )
                        ingestor = DocumentIngester(store=self.workspace.knowledge)
                        num_chunks = ingestor.ingest_text(
                            text=final_output,
                            source_name=doc_id,
                            scope=clean_scope,
                            project_id=out_dest.project_id,
                        )
                        self.workspace.knowledge.update_document(doc_id, "Ready", num_chunks)
                        logger.info("Ingested automation deliverable %s into knowledge store (%d chunks)", filename, num_chunks)
            except Exception as exc:
                logger.warning("Failed to dispatch output to destination: %s", exc)

        total_duration = round(time.time() - start_time, 3)
        completed_iso = datetime.now(timezone.utc).isoformat()

        # Update run record in memory
        run.status = run_status
        run.completed_at = completed_iso
        run.duration_seconds = total_duration
        run.output_result = final_output
        run.error = run_error
        run.step_runs = step_results
        run.retry_count = total_retries
        run.is_retryable = has_retryable_error

        # Update store
        try:
            self.workspace.automations.record_run_completed(
                run_id=run.run_id,
                status=run_status,
                output_result=final_output,
                error=run_error,
                step_runs=step_results,
                completed_at=completed_iso,
                duration_seconds=total_duration,
                retry_count=total_retries,
                is_retryable=has_retryable_error,
            )

            # Update automation definition state
            automation.last_run_at = completed_iso
            automation.last_run_status = run_status.value
            automation.last_finished_at = completed_iso
            automation.last_error = run_error
            automation.retry_count = total_retries
            automation.runtime_status = automation.compute_runtime_status(is_running=False)
            self.workspace.automations.save_automation(automation)
        except Exception as exc:
            logger.warning("Failed to record automation run completion: %s", exc)

        # Dispatch canonical notification
        if hasattr(self.workspace, "notifications") and self.workspace.notifications:
            try:
                from aether.notifications.models import NotificationPriority, NotificationType

                if run_status == RunStatus.WAITING_APPROVAL:
                    notif_type = NotificationType.APPROVAL_REQUIRED
                    notif_priority = NotificationPriority.HIGH
                    title = f"Automation requires approval: {automation.name}"
                    message = f"Automation '{automation.name}' execution is paused awaiting review."
                elif run_status in (RunStatus.SUCCEEDED, RunStatus.COMPLETED):
                    notif_type = NotificationType.ACTION_COMPLETED
                    notif_priority = NotificationPriority.NORMAL
                    title = f"Automation succeeded: {automation.name}"
                    message = f"Run {run.run_id} completed successfully in {total_duration}s."
                else:
                    notif_type = NotificationType.SYSTEM_ALERT
                    notif_priority = NotificationPriority.HIGH
                    title = f"Automation failed: {automation.name}"
                    message = f"Run {run.run_id} failed: {run_error or 'Unknown error'}"

                self.workspace.notifications.notify(
                    workspace_id=getattr(self.workspace, "id", "default"),
                    type=notif_type,
                    title=title,
                    message=message,
                    priority=notif_priority,
                    link_view="automations",
                    link_id=automation.id,
                    target_type="automation",
                    target_id=automation.id,
                )
            except Exception as notif_err:
                logger.debug("Could not dispatch automation notification: %s", notif_err)

        # Log activity
        if hasattr(self.workspace, "activity") and self.workspace.activity:
            try:
                from aether.activity.models import ActivityCategory, ActivityStatus
                category_val = getattr(ActivityCategory, "AUTOMATION", ActivityCategory.SYSTEM)
                act_status = (
                    ActivityStatus.COMPLETED
                    if run_status in (RunStatus.SUCCEEDED, RunStatus.COMPLETED)
                    else ActivityStatus.FAILED
                )
                self.workspace.activity.record_activity(
                    workspace_id=getattr(self.workspace, "id", "default"),
                    category=category_val,
                    title=f"Automation: {automation.name}",
                    description=f"Status: {run_status.value}. Duration: {total_duration}s",
                    status=act_status,
                    metadata={"automation_id": automation.id, "run_id": run.run_id, "trigger_type": trigger_type},
                )
            except Exception as act_err:
                logger.debug("Could not record automation activity: %s", act_err)

        # Dispatch completion event
        if self.event_bus:
            try:
                from aether.coordination.events import Event
                event_type = (
                    "automation:completed"
                    if run_status in (RunStatus.SUCCEEDED, RunStatus.COMPLETED)
                    else ("automation:waiting_approval" if run_status == RunStatus.WAITING_APPROVAL else "automation:failed")
                )
                self.event_bus.publish(
                    Event(
                        type=event_type,
                        source=f"automation:{automation.id}",
                        data={"run_id": run.run_id, "status": run_status.value, "error": run_error},
                    )
                )
            except Exception:
                pass

        return run
