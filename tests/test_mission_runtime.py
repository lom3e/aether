"""
Unit and Integration Tests for MissionRuntime Execution Engine.
Verifies start, pause, resume, cancel, re-run, approval gates, and deliverable harvesting.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from aether.coordination.events import AgentEvent, EventEmitter, EventType
from aether.core.execution import ExecutionResult, ExecutionStatus as CoreExecStatus
from aether.missions.models import (
    Deliverable,
    ExecutionMilestone,
    ExecutionStatus,
    MilestoneExecutionStatus,
    MissionStatus,
)
from aether.missions.runtime import ConflictError, MissionRuntime, NotFoundError
from aether.missions.store import MissionStore
from aether.workspace.workspace import Workspace


class FakeTeam:
    def __init__(self, outputs: list[str] | None = None, emitter: EventEmitter | None = None):
        self.emitter = emitter or EventEmitter()
        self.outputs = list(outputs or ["Step output"])
        self.call_count = 0
        self.config = MagicMock()
        self.config.agents = []

    def run(self, task_instruction: str, session_id: str | None = None, target_agent: str | None = None, cancellation_token=None):
        self.call_count += 1
        if cancellation_token and cancellation_token.is_set():
            return ExecutionResult(success=False, status=CoreExecStatus.INTERRUPTED, error="Interrupted")
        out = self.outputs.pop(0) if self.outputs else "Milestone completed."
        return ExecutionResult(success=True, output=out)


@pytest.fixture
def workspace_with_runtime(tmp_path: Path):
    db_file = tmp_path / "test_missions.db"
    store = MissionStore(db_file)

    ws = MagicMock(spec=Workspace)
    ws.missions = store
    ws.conversations = MagicMock()
    ws.conversations_db_path = str(db_file)
    ws.runtime = None

    events_received = []
    def broadcaster(payload):
        events_received.append(payload)

    runtime = MissionRuntime(workspace=ws, broadcaster=broadcaster)
    return ws, store, runtime, events_received


@pytest.mark.asyncio
async def test_start_mission_and_completion(workspace_with_runtime, tmp_path):
    ws, store, runtime, events = workspace_with_runtime

    fake_emitter = EventEmitter()
    fake_team = FakeTeam(outputs=["Analyzed dependencies", "Patched CVE-1234"], emitter=fake_emitter)
    ws.load_team.return_value = fake_team

    mission = store.create_mission(
        title="Security Mission",
        objective="Analyze vulnerabilities",
        milestones=[
            {"title": "Analysis", "description": "Scan repo", "order_idx": 0},
            {"title": "Remediation", "description": "Patch repo", "order_idx": 1},
        ],
    )

    # Start mission
    exec_run = await runtime.start_mission(mission.id)
    assert exec_run.id.startswith("exec_")
    assert exec_run.run_number == 1
    assert exec_run.status == ExecutionStatus.RUNNING

    # Active execution handle should be running
    handle = runtime._active_executions.get(exec_run.id)
    assert handle is not None
    await handle.task

    # Verify completed state
    final_exec = store.get_execution(exec_run.id)
    assert final_exec is not None
    assert final_exec.status == ExecutionStatus.COMPLETED
    assert final_exec.completed_at is not None

    # Verify milestones
    em_list = store.get_execution_milestones(exec_run.id)
    assert len(em_list) == 2
    assert all(em.status == MilestoneExecutionStatus.COMPLETED for em in em_list)
    assert em_list[0].output == "Analyzed dependencies"
    assert em_list[1].output == "Patched CVE-1234"

    # Verify parent mission
    updated_mission = store.get_mission(mission.id)
    assert updated_mission.status == MissionStatus.COMPLETED
    assert updated_mission.active_execution_id == exec_run.id


@pytest.mark.asyncio
async def test_duplicate_start_rejected(workspace_with_runtime):
    ws, store, runtime, events = workspace_with_runtime

    fake_team = FakeTeam()
    ws.load_team.return_value = fake_team

    mission = store.create_mission(
        title="Lock Test Mission",
        objective="Verify lease",
        milestones=[{"title": "Long step"}],
    )

    # Manually hold a lease to simulate an active running worker
    exec1 = store.create_execution(mission.id)
    store.acquire_execution_lease(mission.id, exec1.id, "other_worker_instance", ttl_seconds=60)

    # Attempting to start mission must raise ConflictError
    with pytest.raises(ConflictError) as exc_info:
        await runtime.start_mission(mission.id)
    assert "already running" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_boundary_safe_pause_and_resume(workspace_with_runtime):
    ws, store, runtime, events = workspace_with_runtime

    fake_team = FakeTeam(outputs=["Step 1 done", "Step 2 done"])
    ws.load_team.return_value = fake_team

    mission = store.create_mission(
        title="Pause Mission",
        objective="Test pause/resume",
        milestones=[
            {"title": "Step 1", "order_idx": 0},
            {"title": "Step 2", "order_idx": 1},
        ],
    )

    # Start mission
    exec_run = await runtime.start_mission(mission.id)
    assert exec_run.status == ExecutionStatus.RUNNING

    # Pause mission
    paused_exec = await runtime.pause_mission(mission.id)
    assert paused_exec.status == ExecutionStatus.INTERRUPTED

    mission_state = store.get_mission(mission.id)
    assert mission_state.status == MissionStatus.INTERRUPTED

    # Resume mission
    resumed_exec = await runtime.resume_mission(mission.id)
    assert resumed_exec.status == ExecutionStatus.RUNNING
    handle = runtime._active_executions.get(resumed_exec.id)
    if handle and handle.task:
        await handle.task

    final_exec = store.get_execution(exec_run.id)
    assert final_exec.status == ExecutionStatus.COMPLETED


@pytest.mark.asyncio
async def test_rerun_mission_creates_new_execution_preserving_history(workspace_with_runtime):
    ws, store, runtime, events = workspace_with_runtime

    fake_team = FakeTeam(outputs=["Run 1 output", "Run 2 output"])
    ws.load_team.return_value = fake_team

    mission = store.create_mission(
        title="Multi-run Mission",
        objective="Test re-runs",
        milestones=[{"title": "Step A"}],
    )

    # Run #1
    exec1 = await runtime.start_mission(mission.id)
    handle1 = runtime._active_executions.get(exec1.id)
    if handle1 and handle1.task:
        await handle1.task

    assert store.get_execution(exec1.id).status == ExecutionStatus.COMPLETED

    # Re-run -> Run #2
    exec2 = await runtime.rerun_mission(mission.id)
    assert exec2.id != exec1.id
    assert exec2.run_number == 2

    handle2 = runtime._active_executions.get(exec2.id)
    if handle2 and handle2.task:
        await handle2.task

    assert store.get_execution(exec2.id).status == ExecutionStatus.COMPLETED

    # Verify both executions exist in history
    all_runs = store.list_executions(mission.id)
    assert len(all_runs) == 2
    assert [r.run_number for r in all_runs] == [2, 1]
    assert all(r.status == ExecutionStatus.COMPLETED for r in all_runs)


@pytest.mark.asyncio
async def test_approval_gate_workflow(workspace_with_runtime):
    ws, store, runtime, events = workspace_with_runtime

    fake_team = FakeTeam(outputs=["Pre-approval work", "Post-approval work"])
    ws.load_team.return_value = fake_team

    mission = store.create_mission(
        title="Deploy Pipeline",
        objective="Automate prod deploy",
        milestones=[
            {"title": "Prepare Manifest", "order_idx": 0},
            {"title": "[Approval Gate] Deploy to Prod", "description": "[Approval] Manual check before release", "order_idx": 1},
            {"title": "Verify Telemetry", "order_idx": 2},
        ],
    )

    # Start mission -> Should run Step 1 then pause at Step 2 awaiting approval
    exec_run = await runtime.start_mission(mission.id)
    handle = runtime._active_executions.get(exec_run.id)
    if handle and handle.task:
        await handle.task

    exec_waiting = store.get_execution(exec_run.id)
    assert exec_waiting.status == ExecutionStatus.AWAITING_APPROVAL
    assert exec_waiting.pending_approval is not None
    appr_id = exec_waiting.pending_approval["id"]

    # User approves
    approved_exec = await runtime.approve_gate(mission.id, appr_id)
    assert approved_exec.status == ExecutionStatus.RUNNING

    handle_resumed = runtime._active_executions.get(exec_run.id)
    if handle_resumed and handle_resumed.task:
        await handle_resumed.task

    # Now mission should be completed
    final_exec = store.get_execution(exec_run.id)
    assert final_exec.status == ExecutionStatus.COMPLETED
    assert len(final_exec.approval_history) == 1
    assert final_exec.approval_history[0]["decision"] == "approved"


@pytest.mark.asyncio
async def test_deliverable_harvesting_during_run(workspace_with_runtime, tmp_path):
    ws, store, runtime, events = workspace_with_runtime

    fake_emitter = EventEmitter()
    report_file = tmp_path / "final_report.md"
    report_file.write_text("# Final Deliverable\nAudit passed.")

    class HarvestingTeam(FakeTeam):
        def run(self, task_instruction, **kwargs):
            # Emit file created event during execution
            self.emitter.emit(
                AgentEvent(
                    event_type=EventType.FILE_CREATED,
                    agent_name="Engineer",
                    task_id="step-1",
                    metadata={"path": str(report_file), "action": "created", "size_bytes": report_file.stat().st_size},
                )
            )
            return ExecutionResult(success=True, output="Generated final_report.md")

    harvest_team = HarvestingTeam(emitter=fake_emitter)
    ws.load_team.return_value = harvest_team

    mission = store.create_mission(
        title="Harvest Mission",
        objective="Produce deliverables",
        milestones=[{"title": "Generate Document"}],
    )

    exec_run = await runtime.start_mission(mission.id)
    handle = runtime._active_executions.get(exec_run.id)
    if handle and handle.task:
        await handle.task

    # Check deliverables
    delivs = store.list_deliverables(mission.id)
    assert len(delivs) == 1
    d = delivs[0]
    assert d.name == "final_report.md"
    assert d.execution_id == exec_run.id
    assert d.sha256 is not None
    assert d.size_bytes > 0


@pytest.mark.asyncio
async def test_deliverable_harvesting_relative_path(workspace_with_runtime, tmp_path):
    ws, store, runtime, events = workspace_with_runtime

    files_dir = tmp_path / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    ws.files_dir = files_dir
    ws.sandbox = MagicMock()
    ws.sandbox.root = files_dir

    runtime_file = files_dir / "runtime_test.txt"
    runtime_file.write_text("Aether Runtime OK")

    fake_emitter = EventEmitter()

    class RelativeHarvestingTeam(FakeTeam):
        def run(self, task_instruction, **kwargs):
            # Emit tool_called with relative path argument as write_file does
            self.emitter.emit(
                AgentEvent(
                    event_type=EventType.TOOL_CALLED,
                    agent_name="Intelligence Lead",
                    task_id="step-1",
                    metadata={
                        "tool_name": "write_file",
                        "arguments": {"path": "runtime_test.txt", "content": "Aether Runtime OK"},
                    },
                )
            )
            return ExecutionResult(success=True, output="Created runtime_test.txt")

    ws.load_team.return_value = RelativeHarvestingTeam(emitter=fake_emitter)

    mission = store.create_mission(
        title="Smoke Test",
        objective="Create small text file",
        milestones=[{"title": "Create test file"}],
    )

    exec_run = await runtime.start_mission(mission.id)
    handle = runtime._active_executions.get(exec_run.id)
    if handle and handle.task:
        await handle.task

    delivs = store.list_deliverables(mission.id)
    assert len(delivs) == 1
    d = delivs[0]
    assert d.name == "runtime_test.txt"
    assert d.execution_id == exec_run.id
    assert d.size_bytes == len("Aether Runtime OK".encode())
    assert d.sha256 is not None

