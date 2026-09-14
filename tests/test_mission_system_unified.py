"""
Comprehensive Unified Integration Test Suite for Aether Mission System.
Tests A through J validating single-path execution via Runtime.execute,
domain models, lineage, quality gate, deterministic progress, and intent tier boundaries.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

from aether.core.execution import (
    ExecutionMode,
    ExecutionResult,
    ExecutionStatus,
    Task,
)
from aether.missions.models import (
    Deliverable,
    Milestone,
    MilestoneExecutionStatus,
    MilestoneStatus,
    Mission,
    MissionPlan,
    MissionResult,
    MissionStep,
    MissionStatus,
    StepStatus,
)
from aether.missions.reviewer import QualityGateEvaluation, QualityGateEvaluator
from aether.missions.runtime import MissionRuntime
from aether.missions.store import MissionStore
from aether.personal.models import IntentTier, UserIntent
from aether.personal.service import PersonalAgentService
from aether.personal.store import PersonalStore
from aether.personal.tasks import PersonalTaskManager
from aether.workspace.workspace import Workspace


# ---------------------------------------------------------------------------
# Test A: Mission creation & persistence
# ---------------------------------------------------------------------------
def test_a_mission_creation_and_persistence(tmp_path: Path):
    db_path = str(tmp_path / "missions_test.db")
    store = MissionStore(db_path)

    milestones_data = [
        {"title": "Initial Scoping", "description": "Scope the objective"},
        {"title": "Execution Phase", "description": "Execute domain tasks"},
    ]
    mission = store.create_mission(
        title="Develop Market Strategy",
        objective="Create a verified market expansion strategy",
        workspace_id="test-ws",
        milestones=milestones_data,
    )

    assert mission.id is not None
    assert mission.title == "Develop Market Strategy"
    assert mission.status in (MissionStatus.DRAFT, MissionStatus.READY)
    assert len(mission.milestones) == 2

    retrieved = store.get_mission(mission.id)
    assert retrieved is not None
    assert retrieved.id == mission.id
    assert retrieved.objective == "Create a verified market expansion strategy"
    assert len(retrieved.milestones) == 2
    assert retrieved.plan is not None
    assert len(retrieved.plan.steps) == 2

    # Verify alias MissionStep is Milestone
    assert MissionStep is Milestone
    assert StepStatus is MilestoneStatus


# ---------------------------------------------------------------------------
# Test B: Milestone plan generation & sequencing
# ---------------------------------------------------------------------------
def test_b_milestone_plan_generation_and_sequencing(tmp_path: Path):
    db_path = str(tmp_path / "plan_test.db")
    store = MissionStore(db_path)

    mission = store.create_mission(
        title="Infrastructure Setup",
        objective="Deploy resilient cluster",
        workspace_id="test-ws",
    )

    m1 = store.create_milestone(mission.id, title="Provision VPC", order_idx=0)
    m2 = store.create_milestone(mission.id, title="Configure Security Groups", order_idx=1, dependencies=[m1.id])
    m3 = store.create_milestone(mission.id, title="Deploy Nodes", order_idx=2, dependencies=[m2.id])

    retrieved = store.get_mission(mission.id)
    assert retrieved is not None
    assert retrieved.plan is not None
    assert len(retrieved.plan.steps) == 3
    assert [s.title for s in retrieved.plan.steps] == [
        "Provision VPC",
        "Configure Security Groups",
        "Deploy Nodes",
    ]
    assert retrieved.plan.steps[1].dependencies == [m1.id]
    assert retrieved.plan.steps[2].dependencies == [m2.id]


# ---------------------------------------------------------------------------
# Test C: Execution through Runtime.execute()
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c_execution_through_runtime(tmp_path: Path):
    ws = Workspace(tmp_path)
    store: MissionStore = ws.missions

    mission = store.create_mission(
        title="Automated Audit",
        objective="Perform security audit",
        workspace_id=ws.name,
        milestones=[{"title": "Scan Vulnerabilities", "description": "Scan open ports"}],
    )

    executed_tasks: list[Task] = []

    class MockRuntime:
        def __init__(self):
            self._agents = {}

        def execute(self, task: Task, progress_callback=None) -> ExecutionResult:
            executed_tasks.append(task)
            return ExecutionResult(
                success=True,
                status=ExecutionStatus.COMPLETED,
                output="Audit scan complete. No critical CVEs found.",
                execution_id=task.id,
                mission_id=task.mission_id,
            )

    ws.runtime = MockRuntime()

    # Pass mock evaluator that always passes quality gate
    mock_evaluator = MagicMock(spec=QualityGateEvaluator)
    mock_evaluator.evaluate = MagicMock()
    async def _mock_eval(**kwargs):
        return QualityGateEvaluation(
            passed=True,
            score=95.0,
            reviewer_agent="Security Reviewer",
            feedback="All audit assertions verified.",
            rules={},
            redlines=[],
        )
    mock_evaluator.evaluate.side_effect = _mock_eval

    runtime = MissionRuntime(workspace=ws, evaluator=mock_evaluator)
    execution = await runtime.start_mission(mission.id)

    # Allow async execution loop to complete
    handle = runtime._active_executions.get(execution.id)
    if handle and handle.task:
        await handle.task

    assert len(executed_tasks) >= 1
    first_task = executed_tasks[0]
    assert first_task.mission_id == mission.id
    assert first_task.parent_id == execution.id
    assert "Scan Vulnerabilities" in first_task.instruction

    completed_mission = store.get_mission(mission.id)
    assert completed_mission.status == MissionStatus.COMPLETED


# ---------------------------------------------------------------------------
# Test D: Lineage preservation
# ---------------------------------------------------------------------------
def test_d_lineage_preservation():
    task = Task(
        instruction="Verify subsystem integrity",
        workspace_id="ws-enterprise",
        session_id="session-456",
        mission_id="msn-789",
        parent_id="exec-101",
        mode=ExecutionMode.DO,
    )

    assert task.workspace_id == "ws-enterprise"
    assert task.session_id == "session-456"
    assert task.mission_id == "msn-789"
    assert task.parent_id == "exec-101"

    result = ExecutionResult(
        success=True,
        status=ExecutionStatus.COMPLETED,
        output="Integrity verified",
        execution_id=task.id,
        mission_id=task.mission_id,
    )

    assert result.mission_id == "msn-789"
    res_dict = result.to_dict()
    assert res_dict["mission_id"] == "msn-789"


# ---------------------------------------------------------------------------
# Test E: Workforce delegation via AgentTool
# ---------------------------------------------------------------------------
def test_e_workforce_delegation_agent_tool(tmp_path: Path):
    from aether.core.runtime import Runtime
    from aether.agents.agent import Agent

    ws = Workspace(tmp_path)
    runtime = Runtime(workspace=ws)

    # Scaffolding coordinator and specialist
    coordinator = Agent(name="coordinator", role="Project Coordinator")
    specialist = Agent(name="data_analyst", role="Data Analyst")

    runtime.register_agent(coordinator)
    runtime.register_agent(specialist)

    task = Task(
        instruction="Conduct quantitative research on energy sector",
        workspace_id=ws.name,
        session_id="sess-e",
        mission_id="msn-e",
        mode=ExecutionMode.DELEGATE,
    )

    result = runtime.execute(task)
    assert result.success is True
    assert result.status == ExecutionStatus.COMPLETED
    assert "energy sector" in result.output.lower() or "quantitative" in result.output.lower()


# ---------------------------------------------------------------------------
# Test F: Real progress derivation
# ---------------------------------------------------------------------------
def test_f_real_progress_derivation(tmp_path: Path):
    db_path = str(tmp_path / "progress_test.db")
    store = MissionStore(db_path)

    mission = store.create_mission(
        title="Multi-stage Project",
        objective="Deliver 4 milestones",
        workspace_id="ws-prog",
        milestones=[
            {"title": "Stage 1"},
            {"title": "Stage 2"},
            {"title": "Stage 3"},
            {"title": "Stage 4"},
        ],
    )

    m_initial = store.get_mission(mission.id)
    assert m_initial.progress == 0

    # Complete first milestone
    m1 = m_initial.milestones[0]
    store.update_milestone(m1.id, status=MilestoneStatus.COMPLETED)
    m_after_1 = store.get_mission(mission.id)
    assert m_after_1.progress == 25

    # Complete second milestone
    m2 = m_initial.milestones[1]
    store.update_milestone(m2.id, status=MilestoneStatus.COMPLETED)
    m_after_2 = store.get_mission(mission.id)
    assert m_after_2.progress == 50

    # Complete third and fourth
    store.update_milestone(m_initial.milestones[2].id, status=MilestoneStatus.COMPLETED)
    store.update_milestone(m_initial.milestones[3].id, status=MilestoneStatus.COMPLETED)
    m_after_all = store.get_mission(mission.id)
    assert m_after_all.progress == 100


# ---------------------------------------------------------------------------
# Test G: Invariant: cannot become COMPLETED before steps resolve
# ---------------------------------------------------------------------------
def test_g_invariant_cannot_complete_before_steps_resolve(tmp_path: Path):
    db_path = str(tmp_path / "invariant_test.db")
    store = MissionStore(db_path)

    mission = store.create_mission(
        title="Strict Pipeline",
        objective="All stages must complete",
        workspace_id="ws-inv",
        milestones=[
            {"title": "Step 1"},
            {"title": "Step 2"},
        ],
    )

    # Mission starts in DRAFT or READY
    assert mission.status != MissionStatus.COMPLETED

    # When 1 of 2 steps completes, mission is not completed
    store.update_milestone(mission.milestones[0].id, status=MilestoneStatus.COMPLETED)
    current = store.get_mission(mission.id)
    assert current.progress == 50
    assert current.status != MissionStatus.COMPLETED


# ---------------------------------------------------------------------------
# Test H: Deliverable recording and referencing
# ---------------------------------------------------------------------------
def test_h_deliverable_recording_and_referencing(tmp_path: Path):
    db_path = str(tmp_path / "deliv_test.db")
    store = MissionStore(db_path)

    mission = store.create_mission(
        title="Artifact Generation",
        objective="Produce verified deliverables",
        workspace_id="ws-deliv",
    )

    deliv_file = tmp_path / "report.md"
    deliv_file.write_text("# Market Summary\nAll indicators positive.")

    import hashlib
    file_bytes = deliv_file.read_bytes()
    sha = hashlib.sha256(file_bytes).hexdigest()

    exec_rec = store.create_execution(mission_id=mission.id)

    deliv = Deliverable(
        id="del_test123",
        mission_id=mission.id,
        execution_id=exec_rec.id,
        name="report.md",
        path=str(deliv_file),
        type="document",
        size_bytes=len(file_bytes),
        sha256=sha,
        status="verified",
    )

    store.add_deliverable(mission.id, deliv)

    retrieved = store.get_mission(mission.id)
    assert len(retrieved.deliverables) == 1
    d = retrieved.deliverables[0]
    assert d.name == "report.md"
    assert d.sha256 == sha
    assert d.status == "verified"


# ---------------------------------------------------------------------------
# Test I: Truthful failure handling
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_i_truthful_failure_handling(tmp_path: Path):
    ws = Workspace(tmp_path)
    store: MissionStore = ws.missions

    mission = store.create_mission(
        title="Faulty Task",
        objective="Run task that fails",
        workspace_id=ws.name,
        milestones=[{"title": "Failing Stage", "description": "Will fail"}],
    )

    class FailingRuntime:
        def __init__(self):
            self._agents = {}

        def execute(self, task: Task, progress_callback=None) -> ExecutionResult:
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error="Fatal connection timeout during stage execution",
                execution_id=task.id,
                mission_id=task.mission_id,
            )

    ws.runtime = FailingRuntime()
    runtime = MissionRuntime(workspace=ws)
    execution = await runtime.start_mission(mission.id)

    handle = runtime._active_executions.get(execution.id)
    if handle and handle.task:
        await handle.task

    failed_mission = store.get_mission(mission.id)
    assert failed_mission.status == MissionStatus.FAILED

    exec_record = store.get_execution(execution.id)
    assert exec_record.status == ExecutionStatus.FAILED
    assert "Fatal connection timeout" in (exec_record.error_message or "")


# ---------------------------------------------------------------------------
# Test J: Conversational prompts do not create missions
# ---------------------------------------------------------------------------
def test_j_conversational_prompts_do_not_create_missions(tmp_path: Path):
    ws = Workspace(tmp_path)
    mission_store: MissionStore = ws.missions
    personal_store = PersonalStore(str(tmp_path / "personal.db"))

    mock_action_executor = MagicMock()
    mock_activity = MagicMock()

    class FastTestRuntime:
        def __init__(self):
            self._agents = {}

        def execute(self, task: Task, progress_callback=None) -> ExecutionResult:
            if task.mode == "delegate":
                return ExecutionResult(
                    success=True,
                    status=ExecutionStatus.COMPLETED,
                    output="Delegated analysis output",
                    execution_id=task.id,
                    metadata={"specialists": ["researcher"], "coordinator": "coordinator"},
                )
            return ExecutionResult(
                success=True,
                status=ExecutionStatus.COMPLETED,
                output="Ciao! Come posso aiutarti oggi?",
                execution_id=task.id,
            )

    ws.runtime = FastTestRuntime()
    task_manager = PersonalTaskManager(store=personal_store)

    service = PersonalAgentService(
        store=personal_store,
        action_executor=mock_action_executor,
        activity_service=mock_activity,
        mission_store=mission_store,
        task_manager=task_manager,
    )
    service.runtime = ws.runtime

    # 1. Conversational prompt (ANSWER tier) -> MUST NOT create mission
    res_answer = service.process_prompt(workspace_id="ws-test", prompt="Ciao, come stai?")
    assert mission_store.list_missions() == []
    assert res_answer.content != ""

    # 2. Delegation prompt (DELEGATE tier) -> MUST create a mission with milestones
    res_delegate = service.process_prompt(
        workspace_id="ws-test",
        prompt="Delega un'analisi strategica completa per Automotive",
    )
    missions_after = mission_store.list_missions()
    assert len(missions_after) == 1
    created_msn = missions_after[0]
    assert "Automotive" in created_msn.title or "Automotive" in created_msn.objective
    assert len(created_msn.milestones) == 3
