"""
P3.2 Release-Grade Hardening: Runtime Crash & Restart Recovery Test Suite.
Verifies:
1. Interrupted action execution recovery (RUNNING and QUEUED transition to FAILED).
2. WAITING_APPROVAL preservation: Pending user approvals survive process restarts intact.
3. Automation run recovery: Interrupted automation pipeline runs transition to FAILED.
4. Mission runtime crash recovery: Orphaned leases cleared and recovery_state flagged.
5. Strict recovery idempotency across consecutive startups.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from aether.actions.models import (
    ActionDefinition,
    ActionExecution,
    ActionExecutionStatus,
    ActionPermissionLevel,
)
from aether.actions.registry import ActionRegistry
from aether.actions.store import ActionStore
from aether.actions.executor import ActionExecutor
from aether.automation.models import AutomationDefinition, PipelineStep, TriggerConfig, TriggerType, RunStatus
from aether.automation.store import AutomationStore, AutomationRunRecord
from aether.missions.models import MissionExecution, ExecutionStatus
from aether.missions.store import MissionStore
from aether.missions.runtime import MissionRuntime
from aether.workspace.workspace import Workspace


def test_action_store_crash_recovery_preserves_waiting_approval(tmp_path: Path):
    """
    Verifies that when an application restarts after an ungraceful crash:
    - Executions in RUNNING or QUEUED are safely marked FAILED.
    - Executions in WAITING_APPROVAL are preserved so the user can still confirm/decline them.
    - Terminal executions (SUCCEEDED, REJECTED) are untouched.
    - Recovery is strictly idempotent.
    """
    db_path = tmp_path / "actions.db"
    store = ActionStore(db_path)

    # 1. Seed executions in various states
    e_running = ActionExecution(
        id="exec-run-1",
        action_id="test.deploy",
        workspace_id="ws-test",
        status=ActionExecutionStatus.RUNNING,
        input_data={"service": "api"},
    )
    e_queued = ActionExecution(
        id="exec-queue-1",
        action_id="test.deploy",
        workspace_id="ws-test",
        status=ActionExecutionStatus.QUEUED,
        input_data={"service": "worker"},
    )
    e_waiting = ActionExecution(
        id="exec-wait-1",
        action_id="test.deploy",
        workspace_id="ws-test",
        status=ActionExecutionStatus.WAITING_APPROVAL,
        input_data={"service": "database"},
    )
    e_succeeded = ActionExecution(
        id="exec-succ-1",
        action_id="test.deploy",
        workspace_id="ws-test",
        status=ActionExecutionStatus.SUCCEEDED,
        input_data={"service": "redis"},
    )

    store.save_execution(e_running)
    store.save_execution(e_queued)
    store.save_execution(e_waiting)
    store.save_execution(e_succeeded)

    # Simulate process restart crash recovery
    recovered_count = store.recover_interrupted_executions()
    assert recovered_count == 2

    # Verify RUNNING -> FAILED
    r_run = store.get_execution("exec-run-1")
    assert r_run is not None
    assert r_run.status == ActionExecutionStatus.FAILED
    assert "interrupted by application restart/crash" in r_run.error_message

    # Verify QUEUED -> FAILED
    r_queue = store.get_execution("exec-queue-1")
    assert r_queue is not None
    assert r_queue.status == ActionExecutionStatus.FAILED
    assert "interrupted by application restart/crash" in r_queue.error_message

    # Verify WAITING_APPROVAL is strictly preserved!
    r_wait = store.get_execution("exec-wait-1")
    assert r_wait is not None
    assert r_wait.status == ActionExecutionStatus.WAITING_APPROVAL
    assert r_wait.error_message is None

    # Verify SUCCEEDED is untouched
    r_succ = store.get_execution("exec-succ-1")
    assert r_succ is not None
    assert r_succ.status == ActionExecutionStatus.SUCCEEDED

    # Verify Idempotency: Second recovery pass changes 0 records
    assert store.recover_interrupted_executions() == 0

    # Ensure the recovered WAITING_APPROVAL execution can still be approved
    reg = ActionRegistry()
    reg.register(
        ActionDefinition(
            id="test.deploy",
            name="Deploy",
            description="Deploy service",
            permission_level=ActionPermissionLevel.SENSITIVE_MUTATION,
            requires_confirmation=True,
        ),
        handler=lambda inp, ws: {"deployed": inp["service"]},
    )
    executor = ActionExecutor(registry=reg, store=store)
    approved = executor.approve("exec-wait-1", approver="admin_post_restart")
    assert approved.status == ActionExecutionStatus.SUCCEEDED
    assert approved.output_data == {"deployed": "database"}


def test_automation_store_interrupted_runs_recovery(tmp_path: Path):
    """
    Verifies that automation pipeline runs interrupted by crash transition to FAILED.
    """
    db_path = tmp_path / "automations.db"
    store = AutomationStore(db_path)

    # Save active definition
    auto = AutomationDefinition(
        id="auto-rec-1",
        name="Nightly Sync",
        enabled=True,
        trigger=TriggerConfig(type=TriggerType.SCHEDULE, cron="0 0 * * *"),
        steps=[PipelineStep(id="step1", name="Fetch logs")],
    )
    store.save_automation(auto)

    # Save an interrupted run in 'running' state
    run_interrupted = AutomationRunRecord(
        run_id="run-int-1",
        automation_id="auto-rec-1",
        trigger_type="cron",
        status="running",
        started_at="2026-09-28T20:00:00Z",
    )
    store.record_run_started(run_interrupted)

    # Save a finished run in 'succeeded' state
    run_done = AutomationRunRecord(
        run_id="run-done-1",
        automation_id="auto-rec-1",
        trigger_type="cron",
        status="running",
        started_at="2026-09-28T19:00:00Z",
    )
    store.record_run_started(run_done)
    store.record_run_completed(run_id="run-done-1", status=RunStatus.SUCCEEDED, output_result="done")

    # Execute recovery
    recovered_runs = store.recover_interrupted_runs()
    assert recovered_runs == 1

    # Verify statuses
    r1 = store.get_run("run-int-1")
    assert r1 is not None
    assert r1.status == "failed"
    assert "interrupted" in r1.error.lower()

    r2 = store.get_run("run-done-1")
    assert r2 is not None
    assert r2.status == "succeeded"

    # Idempotency check
    assert store.recover_interrupted_runs() == 0


def test_mission_runtime_stale_executions_recovery(tmp_path: Path):
    """
    Verifies MissionRuntime crash recovery:
    - Clears orphaned leases and resets execution recovery_state.
    - Preserves goals and mission deliverables.
    """
    ws_dir = tmp_path / "ws_recovery"
    ws = Workspace.get_or_init(ws_dir, "Recovery WS")

    mission_store = ws.missions
    runtime = MissionRuntime(ws)

    # Seed parent mission first to satisfy foreign key constraint
    from aether.missions.models import Mission
    m = Mission(
        id="msn-recover-test",
        workspace_id=ws.name,
        title="Recovery Test Mission",
        objective="Verify crash recovery",
    )
    mission_store.save_mission(m)

    # Seed an execution that was running when process terminated
    exec_orphaned = MissionExecution(
        id="mexec-orphaned-1",
        mission_id="msn-recover-test",
        run_number=1,
        team_name="Engineering Core",
        status=ExecutionStatus.RUNNING,
        lease_owner="worker-pid-9999",
        lease_expires_at="2026-09-28T20:00:00Z",
        heartbeat_at="2026-09-28T19:59:00Z",
        recovery_state="none",
    )
    mission_store.save_execution(exec_orphaned)

    # Execute runtime crash recovery hook
    recovered = runtime.recover_stale_executions()
    assert "mexec-orphaned-1" in recovered

    # Verify execution state after recovery
    updated = mission_store.get_execution("mexec-orphaned-1")
    assert updated is not None
    assert updated.lease_owner is None
    assert updated.recovery_state == "recovered_from_crash"

    # Idempotent second run
    assert runtime.recover_stale_executions() == []
