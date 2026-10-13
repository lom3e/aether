"""
Closing the loop for coding runs: lifecycle events -> mission state -> verified deliverables -> memory.

A coding run reports what happened (state, files changed, independent verification, authorised test results). This
module turns those facts into the mission's own truth:

* every lifecycle event is published on the personal event hub with a common envelope (workspace, mission, run, type),
* the mission's stages follow the run: implementation done only if the run was independently verified, tests done
  only if an authorised test run actually passed,
* changed files become deliverables, ``verified`` ONLY when the quality gate passes with technical evidence
  (verified run + passing tests when the mission requires them), never because a file exists,
* only then is the outcome written to memory (as verified), once per mission.

The listener is registered process-wide (CodingRunRegistry.subscribe) and is idempotent: replaying an event does not
duplicate deliverables or memories.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import threading
from typing import Any
import uuid

logger = logging.getLogger(__name__)

TERMINAL_RUN_STATUSES = {"completed", "failed", "timed_out", "cancelled", "requires_rework"}
TERMINAL_EVENTS = {"run_completed", "run_failed", "run_timed_out", "run_cancelled", "tests_run", "run_interrupted_by_restart"}


def register_coding_finalizer() -> None:
    """Attaches the finalizer to the process-wide registry (a registry also attaches it itself on first event)."""
    from aether.coding.runs import get_run_registry
    get_run_registry()._ensure_default_subscribers()


_LOCKS_GUARD = threading.Lock()
_MISSION_LOCKS: dict[str, threading.RLock] = {}


def _mission_lock(mission_id: str) -> threading.RLock:
    with _LOCKS_GUARD:
        return _MISSION_LOCKS.setdefault(mission_id, threading.RLock())


def _run_coro(coro: Any) -> Any:
    """Runs a coroutine to completion from sync code, even if this thread already has a running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict[str, Any] = {}

    def _t() -> None:
        try:
            box["v"] = asyncio.run(coro)
        except Exception as exc:  # pragma: no cover
            box["e"] = exc
    th = threading.Thread(target=_t)
    th.start()
    th.join()
    if "e" in box:
        raise box["e"]
    return box.get("v")


class CodingMissionFinalizer:
    """Callable subscriber: ``fn(event, run, data, seq)``."""

    def __call__(self, event: str, run: Any, data: dict[str, Any], seq: int) -> None:
        from aether.workspace.workspace import Workspace
        ws_key = run.task.workspace_id or (run.metadata or {}).get("workspace_id")
        ws = Workspace.resolve_unique(ws_key)
        if ws is None:
            return
        self._publish(ws, event, run, data, seq)
        mission_id = run.task.mission_id or (run.metadata or {}).get("mission_id")
        if mission_id and event in TERMINAL_EVENTS:
            try:
                self.finalize(ws, mission_id, run)
            except Exception as exc:
                logger.warning("Coding mission finalization failed for %s: %s", mission_id, exc)

    # -- events ---------------------------------------------------------------------------------------------
    @staticmethod
    def _publish(ws: Any, event: str, run: Any, data: dict[str, Any], seq: int) -> None:
        try:
            from aether.personal.events import get_personal_event_hub
            get_personal_event_hub().publish(
                workspace_id=ws.id, event_type="coding_run_update",
                data={
                    "workspace_id": ws.id, "mission_id": run.task.mission_id, "run_id": run.id, "event": event, "seq": seq,
                    "status": run.status.value, "provider_id": run.provider_id,
                    "model": (run.metadata or {}).get("model") or run.task.model,
                    "modified_files": list(run.result.modified_files) if run.result else [],
                    "verification_passed": run.result.verification_passed if run.result else None,
                },
            )
        except Exception as exc:
            logger.debug("Could not publish coding event: %s", exc)

    # -- mission state ---------------------------------------------------------------------------------------
    def finalize(self, ws: Any, mission_id: str, run: Any) -> None:
        """Serialised per mission: two runs ending together must not interleave their read-modify-write of the mission."""
        with _mission_lock(mission_id):
            self._finalize_locked(ws, mission_id, run)

    def _finalize_locked(self, ws: Any, mission_id: str, run: Any) -> None:
        from aether.missions.models import Deliverable, ExecutionStatus, MilestoneStatus, MissionStatus
        from aether.missions.reviewer import QualityGateEvaluator

        store = ws.missions
        mission = store.get_mission(mission_id)
        if mission is None:
            return
        meta = dict(mission.metadata or {})
        # A mission that already reached a protected terminal state is not rewritten by an event of ANOTHER run
        # (a late failure must not undo a verified completion, nor resurrect a cancelled mission). The late event is
        # kept as evidence in the mission metadata; replays of the owning run stay idempotent.
        owner = meta.get("completed_by_run")
        if (mission.status in (MissionStatus.COMPLETED, MissionStatus.CANCELLED)
                and run.id != owner and (mission.status == MissionStatus.CANCELLED or owner is not None or run.id not in meta.get("coding_run_ids", []))):
            late = list(meta.get("ignored_late_runs") or [])
            entry = {"run_id": run.id, "status": run.status.value, "ignored_at": datetime.now(timezone.utc).isoformat(),
                     "mission_status": mission.status.value}
            if not any(e.get("run_id") == run.id and e.get("status") == entry["status"] for e in late):
                late.append(entry)
                meta["ignored_late_runs"] = late
                store.update_mission(mission_id, metadata=meta)
            return
        required = list(meta.get("required_evidence") or [])
        milestones = sorted(mission.milestones, key=lambda m: m.order_idx)
        impl = milestones[0] if milestones else None
        tests_ms = milestones[1] if len(milestones) > 1 else None

        status = run.status.value
        result = run.result
        test_run = (run.metadata or {}).get("test_run")
        verified_run = bool(result and result.verification_passed is True and status == "completed")
        needs_tests = "tests_passed" in required

        # one mission execution per mission for coding missions
        exec_id = meta.get("coding_execution_id")
        if not exec_id:
            exec_id = store.create_execution(mission_id=mission_id, team_name=None, status=ExecutionStatus.RUNNING).id
            meta["coding_execution_id"] = exec_id
            store.update_mission(mission_id, active_execution_id=exec_id)
        meta["coding_run_ids"] = sorted(set(meta.get("coding_run_ids", [])) | {run.id})

        def set_ms(ms: Any, status: Any) -> None:
            # The template row and the active execution's own row are both read by get_mission().
            store.update_milestone(ms.id, status=status)
            exec_status = MilestoneStatus.PENDING if status == MilestoneStatus.WAITING else status
            store.update_execution_milestone(exec_id, ms.id, status=exec_status.value)

        # stage: implementation
        if impl:
            if status in ("running", "waiting_for_interaction", "waiting_for_approval", "queued"):
                set_ms(impl, MilestoneStatus.RUNNING)
            elif verified_run:
                set_ms(impl, MilestoneStatus.COMPLETED)
            else:
                set_ms(impl, MilestoneStatus.FAILED)
        # stage: authorised tests
        run_failed = status in ("failed", "timed_out", "cancelled", "requires_rework") or (status == "completed" and not verified_run)
        if tests_ms is not None:
            if run_failed and not test_run:
                set_ms(tests_ms, MilestoneStatus.SKIPPED)   # tests are meaningless without a verified implementation
            elif test_run:
                set_ms(tests_ms, MilestoneStatus.COMPLETED if test_run.get("passed") else MilestoneStatus.FAILED)
            elif verified_run and needs_tests:
                set_ms(tests_ms, MilestoneStatus.WAITING)

        # deliverables = what the run really changed (hashes of files on disk)
        deliverables: list[Deliverable] = []
        existing = {d.path: d for d in store.list_deliverables(mission_id)}
        project = Path(run.task.project_path).resolve()
        for rel in (result.modified_files if result else []):
            p = (project / rel).resolve()
            if not p.is_file():
                continue
            data = p.read_bytes()
            d = existing.get(str(p)) or Deliverable(
                id=f"del_{uuid.uuid4().hex[:12]}", mission_id=mission_id, execution_id=exec_id,
                milestone_id=impl.id if impl else None, name=rel, path=str(p),
                type="code" if p.suffix in (".py", ".ts", ".js", ".rs", ".go", ".sh") else "document",
            )
            d.size_bytes, d.sha256, d.execution_id = len(data), hashlib.sha256(data).hexdigest(), exec_id
            d.metadata = {**(d.metadata or {}), "origin": "coding_run", "run_id": run.id, "provider_id": run.provider_id}
            d.status = "needs_revision" if run_failed else (d.status if d.status == "verified" else "draft")
            store.add_deliverable(mission_id, d)
            deliverables.append(d)

        evidence = {"coding_runs": [{
            "id": run.id, "status": status, "provider_id": run.provider_id,
            "model": (run.metadata or {}).get("model"),
            "verification_passed": result.verification_passed if result else None, "test_run": test_run,
        }]}

        # decide the mission's state from facts
        if status not in TERMINAL_RUN_STATUSES:
            return   # the run is still alive (running / waiting for the user): the mission keeps its current state
        if run_failed:
            if status == "requires_rework":
                meta["needs_rework"] = True
                err = ("The coding agent changed files but its work did not pass independent verification: it needs rework. "
                       + (run.error or (result.error if result else None) or ""))
            else:
                err = (run.error or (result.error if result else None) or "The coding run did not pass independent verification.")
            err = err.strip()
            store.update_execution(exec_id, status=ExecutionStatus.FAILED, error_message=err)
            store.update_mission(mission_id, status=MissionStatus.FAILED, metadata=meta)
            return
        if needs_tests and not test_run:
            store.update_mission(mission_id, status=MissionStatus.WAITING, metadata=meta)   # waiting for the authorised test run
            return
        if test_run and not test_run.get("passed"):
            store.update_execution(exec_id, status=ExecutionStatus.FAILED, error_message="The authorised test run did not pass.")
            store.update_mission(mission_id, status=MissionStatus.FAILED, metadata=meta)
            return
        if not verified_run:
            return

        evaluation = _run_coro(QualityGateEvaluator().evaluate(
            mission_title=mission.title, mission_objective=mission.objective, deliverables=deliverables,
            completed_context=[result.summary or ""], team=None, workspace=ws, evidence=evidence,
            required_evidence=required or ["coding_run_verified"],
        ))
        if not evaluation.passed:
            store.update_execution(exec_id, status=ExecutionStatus.FAILED, error_message=evaluation.feedback)
            store.update_mission(mission_id, status=MissionStatus.FAILED, metadata=meta)
            return

        for d in deliverables:
            d.status = "verified"
            d.metadata = {**(d.metadata or {}), "verification_method": evaluation.method,
                          "semantically_verified": evaluation.semantically_verified, "not_checked": list(evaluation.not_checked),
                          "quality_score": evaluation.score}
            store.add_deliverable(mission_id, d)
        store.update_execution(exec_id, status=ExecutionStatus.COMPLETED)
        meta["completed_by_run"] = run.id
        store.update_mission(mission_id, status=MissionStatus.COMPLETED, metadata=meta)
        try:
            from aether.memory.ingestion import MemoryIngestionService
            MemoryIngestionService.ingest_mission_outcome(
                memory_store=ws.memory, workspace_id=ws.id, mission_id=mission_id, execution_id=exec_id,
                title=mission.title, objective=mission.objective,
                stage_outputs=[f"Files changed: {', '.join(result.modified_files)}", result.summary or "",
                               f"Tests: exit {test_run.get('exit_code')}" if test_run else ""],
                eval_result=evaluation, deliverables=deliverables,
                evidence={"coding_runs": [run.id], "provider_id": run.provider_id,
                          "model": (run.metadata or {}).get("model"), "tests_passed": bool(test_run and test_run.get("passed"))},
                knowledge_graph_store=getattr(ws, "knowledge_graph", None),
            )
        except Exception as exc:
            logger.warning("Outcome memory write failed: %s", exc)
