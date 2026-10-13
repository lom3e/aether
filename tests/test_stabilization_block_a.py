"""
Stabilization block A: executor/mission/finalizer state coherence. Real Workspace + stores in tmp dirs, no network,
no LLM, no external agents (the coding orchestrator is a stub where a dispatch outcome has to be forced).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from aether.actions.models import ActionExecution
from aether.coding.models import CodingExecutionStatus as S, CodingResult, CodingTask, CodingTaskExecution
from aether.coding.runs import ProjectBusyError
from aether.missions.coding_outcomes import CodingMissionFinalizer
from aether.missions.runtime import MissionRuntime
from aether.workspace.workspace import Workspace


@pytest.fixture
def ctx(tmp_path):
    ws = Workspace.init(tmp_path / "ws", "Block A WS")
    project = tmp_path / "proj"
    project.mkdir()
    (project / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    yield ws, project
    try:
        ws.personal.shutdown()
    except Exception:
        pass


def make_mission(ws, evidence=("coding_run_verified", "tests_passed")):
    return ws.missions.create_mission(
        title="Coding: add", objective="Implement calc.add", workspace_id=ws.id, status="running",
        metadata={"kind": "coding", "required_evidence": list(evidence)},
        milestones=[{"title": "impl", "description": "d", "order_idx": 0}, {"title": "tests", "description": "d", "order_idx": 1}])


def snapshot(ws, mission_id):
    m = ws.missions.get_mission(mission_id)
    return m, m.status.value, [x.status.value for x in sorted(m.milestones, key=lambda x: x.order_idx)]


# --- A1: evaluator compatibility (signature inspection, never blind retry) ----------------------------------------

class Legacy:
    async def evaluate(self, mission_title, mission_objective, deliverables, completed_context, team=None, workspace=None): ...

class Modern:
    async def evaluate(self, mission_title, mission_objective, deliverables, completed_context, team=None, workspace=None,
                       evidence=None, required_evidence=None): ...

class Kw:
    async def evaluate(self, **kwargs): ...


def test_evaluator_parameters_are_read_from_the_signature():
    assert "evidence" not in MissionRuntime._evaluator_parameters(Legacy())
    assert {"evidence", "required_evidence"} <= MissionRuntime._evaluator_parameters(Modern())
    assert MissionRuntime._evaluator_parameters(Kw()) is None            # accepts anything


# --- A2: requires_rework ------------------------------------------------------------------------------------------

def test_requires_rework_is_not_waiting_not_deliverable_and_writes_no_memory(ctx):
    ws, project = ctx
    mission = make_mission(ws)
    run = CodingTaskExecution(id="r1", task=CodingTask(instruction="x", project_path=str(project), workspace_id=ws.id, mission_id=mission.id),
                              provider_id="antigravity", status=S.REQUIRES_REWORK)
    run.result = CodingResult(success=False, status=S.REQUIRES_REWORK, provider_id="antigravity",
                              modified_files=["calc.py"], verification_passed=False)
    CodingMissionFinalizer().finalize(ws, mission.id, run)
    m, status, ms = snapshot(ws, mission.id)
    assert status == "failed" and ms == ["failed", "skipped"]
    assert m.metadata.get("needs_rework") is True
    assert all(d.status == "needs_revision" for d in ws.missions.list_deliverables(mission.id))
    assert not ws.memory.list_memories(workspace_id=ws.id, mission_id=mission.id)
    ex = ws.missions.list_executions(mission.id)[0]
    assert ex.status.value == "failed" and "rework" in (ex.error_message or "").lower()


def test_still_running_run_does_not_touch_the_mission_state(ctx):
    ws, project = ctx
    mission = make_mission(ws)
    run = CodingTaskExecution(id="r2", task=CodingTask(instruction="x", project_path=str(project), workspace_id=ws.id, mission_id=mission.id),
                              provider_id="antigravity", status=S.WAITING_FOR_INTERACTION)
    CodingMissionFinalizer().finalize(ws, mission.id, run)
    _, status, _ = snapshot(ws, mission.id)
    assert status == "running"


# --- A3 / A5: executor dispatch ---------------------------------------------------------------------------------------

def _delegate(ws, project, orchestrator):
    ex = ws.actions
    definition = ex.registry.get("coding.delegate")
    execution = ActionExecution(id="ax-test", action_id="coding.delegate", workspace_id=ws.id,
                                input_data={"instruction": "Implement calc.add", "project_path": str(project), "provider_id": "claude_code"},
                                metadata={"allowed_paths": [str(project)]})
    with patch("aether.coding.orchestrator.get_coding_orchestrator", return_value=orchestrator):
        return ex, execution, ex._execute_builtin_action(definition, execution)


def stub_orchestrator(delegate):
    return SimpleNamespace(bind_run_store=lambda store: store, delegate_task=delegate)


def test_dispatch_failure_does_not_leave_a_running_mission(ctx):
    ws, project = ctx

    def busy(*a, **k):
        raise ProjectBusyError(str(project), "run-prev", "a previous run may still be writing")

    with pytest.raises(ProjectBusyError):
        _delegate(ws, project, stub_orchestrator(busy))
    missions = [m for m in ws.missions.list_missions(workspace_id=ws.id)]
    assert len(missions) == 1
    m = ws.missions.get_mission(missions[0].id)
    assert m.status.value == "failed"                                     # not "running" forever
    assert m.metadata["dispatch_error"]["type"] == "ProjectBusyError"      # the proof of the failure is kept
    assert [x.status.value for x in m.milestones] == ["skipped", "skipped"]
    ex = ws.missions.list_executions(m.id)[0]
    assert ex.status.value == "failed" and "ProjectBusyError" in ex.error_message


def _waiting_run(project, ws_id, status):
    task = CodingTask(instruction="x", project_path=str(project), workspace_id=ws_id)
    run = CodingTaskExecution(id="exec-w", task=task, provider_id="antigravity", status=status)
    run.interaction_prompt = "Which file?"
    return run


@pytest.mark.parametrize("status,awaiting", [(S.WAITING_FOR_INTERACTION, "interaction"), (S.WAITING_FOR_APPROVAL, "approval")])
def test_waiting_run_is_accepted_but_not_terminal_verified_or_deliverable(ctx, status, awaiting):
    ws, project = ctx
    _, execution, out = _delegate(ws, project, stub_orchestrator(lambda *a, **k: _waiting_run(project, ws.id, status)))
    assert out["success"] is True and out["status"] == status.value          # request accepted, nothing failed
    assert out["run_terminal"] is False and out["awaiting"] == awaiting
    assert out["verified"] is False and out["deliverable_ready"] is False
    assert execution.metadata["coding_run_state"] == status.value


def test_completed_unverified_run_is_terminal_but_not_a_deliverable(ctx):
    ws, project = ctx
    run = _waiting_run(project, ws.id, S.COMPLETED)
    run.result = CodingResult(success=False, status=S.COMPLETED, provider_id="antigravity", verification_passed=False)
    _, _, out = _delegate(ws, project, stub_orchestrator(lambda *a, **k: run))
    assert out["run_terminal"] is True and out["verified"] is False and out["deliverable_ready"] is False and out["success"] is False


def test_verified_run_is_a_deliverable(ctx):
    ws, project = ctx
    run = _waiting_run(project, ws.id, S.COMPLETED)
    run.result = CodingResult(success=True, status=S.COMPLETED, provider_id="antigravity", verification_passed=True, modified_files=["calc.py"])
    _, _, out = _delegate(ws, project, stub_orchestrator(lambda *a, **k: run))
    assert out["run_terminal"] and out["verified"] and out["deliverable_ready"] and out["success"]


# A4 is exercised behaviourally in tests/test_legacy_delegate_truth.py (real PersonalAgentService, failing mission store).
