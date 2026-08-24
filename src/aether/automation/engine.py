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
    OutputType,
    PipelineStep,
    RunStatus,
    StepRunResult,
)

logger = logging.getLogger(__name__)


class AutomationEngine:
    """Executes automation workflows with DAG step dependencies and output dispatching."""

    def __init__(self, workspace: Any, event_bus: Any = None) -> None:
        self.workspace = workspace
        self.event_bus = event_bus

    async def execute_automation(
        self,
        automation: AutomationDefinition,
        trigger_type: str = "manual",
        trigger_payload: dict[str, Any] | None = None,
    ) -> AutomationRunRecord:
        start_time = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = trigger_payload or {}

        run = AutomationRunRecord(
            automation_id=automation.id,
            automation_name=automation.name,
            trigger_type=trigger_type,
            status=RunStatus.RUNNING,
            started_at=now_iso,
            input_payload=payload,
        )

        # Persist started run in store
        try:
            self.workspace.automations.record_run_started(run)
        except Exception as exc:
            logger.warning("Failed to record automation run start: %s", exc)

        # Dispatch event
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
        run_status = RunStatus.COMPLETED
        run_error: str | None = None

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

        if run_status == RunStatus.COMPLETED:
            # If no steps defined, execute a single step using trigger payload
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

                try:
                    # Run via team or agent
                    if hasattr(team, "run"):
                        result = await asyncio.to_thread(team.run, prompt)
                        step_output = result.output if hasattr(result, "output") else str(result)
                        if hasattr(result, "success") and not result.success:
                            step_status = "failed"
                            step_err = getattr(result, "error", "Step execution failed")
                    else:
                        step_output = f"[Simulated execution for {step.name}]: Completed."
                except Exception as exc:
                    step_status = "failed"
                    step_err = str(exc)
                    logger.error("Error executing step %s: %s", step.id, exc)

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

                # Add step output to context variables
                context_vars[f"{step.id}_output"] = step_output
                context_vars[f"step_{len(step_results)}_output"] = step_output
                final_output = step_output

                if step_status == "failed":
                    run_status = RunStatus.FAILED
                    run_error = f"Step '{step.name}' failed: {step_err}"
                    break

        # Output dispatching
        if run_status == RunStatus.COMPLETED and automation.output_destination and final_output:
            out_dest = automation.output_destination
            try:
                if out_dest.type == OutputType.FILE and out_dest.target_path:
                    # Target path relative to workspace or absolute
                    dest_file = (self.workspace.root / out_dest.target_path.lstrip("/")).resolve()
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    dest_file.write_text(final_output, encoding="utf-8")
                    logger.info("Saved automation output to %s", dest_file)

                elif out_dest.type == OutputType.KNOWLEDGE:
                    # Ingest output into knowledge store
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
            )

            # Update automation definition's last run info
            automation.last_run_at = completed_iso
            automation.last_run_status = run_status.value
            self.workspace.automations.save_automation(automation)
        except Exception as exc:
            logger.warning("Failed to record automation run completion: %s", exc)

        # Dispatch completion event
        if self.event_bus:
            try:
                from aether.coordination.events import Event
                self.event_bus.publish(
                    Event(
                        type="automation:completed" if run_status == RunStatus.COMPLETED else "automation:failed",
                        source=f"automation:{automation.id}",
                        data={"run_id": run.run_id, "status": run_status.value, "error": run_error},
                    )
                )
            except Exception:
                pass

        return run
