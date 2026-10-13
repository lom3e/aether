"""
Coding run -> mission finalisation with real stores (tmp Workspace, real files, real hashes):
events on the shared hub, stage state from facts, deliverables verified only with technical evidence,
memory written only once and only when verified.
"""
from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from fake_agent_script import write_agent_script

from aether.coding.models import CodingExecutionStatus as S, CodingResult, CodingTask, CodingTaskExecution
from aether.missions.coding_outcomes import CodingMissionFinalizer
from aether.personal.events import get_personal_event_hub
from aether.workspace.workspace import Workspace


@pytest.fixture(autouse=True)
def no_reviewer_model(monkeypatch):
    """The gate must stay deterministic here: never let a test reach an implicitly discovered local model."""
    monkeypatch.setattr("aether.core.runtime.Runtime.resolve_provider", lambda self: None)


@pytest.fixture
def ctx(tmp_path):
    ws = Workspace.init(tmp_path / "ws", "Coding Final WS")
    project = tmp_path / "proj"
    project.mkdir()
    (project / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    mission = ws.missions.create_mission(
        title="Coding: add", objective="Implement calc.add", workspace_id=ws.id, status="running",
        metadata={"kind": "coding", "required_evidence": ["coding_run_verified", "tests_passed"]},
        milestones=[{"title": "impl", "description": "d", "order_idx": 0}, {"title": "tests", "description": "d", "order_idx": 1}])
    yield ws, project, mission
    try:
        ws.personal.shutdown()
    except Exception:
        pass


def make_run(ws, project, mission_id, status=S.COMPLETED, verified=True, files=("calc.py",), test_run=None):
    task = CodingTask(instruction="Implement calc.add", project_path=str(project), workspace_id=ws.id, mission_id=mission_id)
    run = CodingTaskExecution(id="run-1", task=task, provider_id="antigravity", status=status)
    run.result = CodingResult(success=verified, status=status, provider_id="antigravity", summary="Added add()",
                              modified_files=list(files), verification_passed=verified)
    run.metadata["model"] = "gemini-test"
    if test_run:
        run.metadata["test_run"] = test_run
    return run


def statuses(ws, mission_id):
    m = ws.missions.get_mission(mission_id)
    return m.status.value, [x.status.value for x in sorted(m.milestones, key=lambda x: x.order_idx)]


def test_verified_run_without_tests_waits_and_never_verifies(ctx):
    ws, project, mission = ctx
    CodingMissionFinalizer().finalize(ws, mission.id, make_run(ws, project, mission.id))
    status, ms = statuses(ws, mission.id)
    assert status == "waiting" and ms[0] == "completed"
    dels = ws.missions.list_deliverables(mission.id)
    assert dels and all(d.status != "verified" for d in dels)
    assert dels[0].sha256 == hashlib.sha256((project / "calc.py").read_bytes()).hexdigest()
    assert not ws.memory.list_memories(workspace_id=ws.id, mission_id=mission.id)


def test_passing_authorised_tests_complete_mission_and_write_memory_once(ctx):
    ws, project, mission = ctx
    fin = CodingMissionFinalizer()
    fin.finalize(ws, mission.id, make_run(ws, project, mission.id))
    run = make_run(ws, project, mission.id, test_run={"passed": True, "exit_code": 0, "runner": "pytest"})
    fin.finalize(ws, mission.id, run)
    fin.finalize(ws, mission.id, run)   # replay: idempotent
    status, ms = statuses(ws, mission.id)
    assert status == "completed" and ms == ["completed", "completed"]
    dels = ws.missions.list_deliverables(mission.id)
    assert len(dels) == 1 and dels[0].status == "verified"
    assert dels[0].metadata["origin"] == "coding_run" and dels[0].metadata["run_id"] == "run-1"
    assert len(ws.missions.list_executions(mission.id)) == 1
    mems = ws.memory.list_memories(workspace_id=ws.id, mission_id=mission.id)
    assert len(mems) == 1 and "verified" in mems[0].tags
    assert mems[0].provenance.verification_status == "verified"


def test_failing_tests_fail_the_mission(ctx):
    ws, project, mission = ctx
    run = make_run(ws, project, mission.id, test_run={"passed": False, "exit_code": 1, "runner": "pytest"})
    CodingMissionFinalizer().finalize(ws, mission.id, run)
    status, ms = statuses(ws, mission.id)
    assert status == "failed" and ms[1] == "failed"
    assert all(d.status != "verified" for d in ws.missions.list_deliverables(mission.id))


def test_unverified_or_failed_run_fails_and_marks_nothing_verified(ctx):
    ws, project, mission = ctx
    CodingMissionFinalizer().finalize(ws, mission.id, make_run(ws, project, mission.id, verified=False))
    status, ms = statuses(ws, mission.id)
    assert status == "failed" and ms[0] == "failed"


def test_event_is_published_with_common_envelope(ctx):
    ws, project, mission = ctx
    q = get_personal_event_hub().subscribe(ws.id)
    run = make_run(ws, project, mission.id)
    CodingMissionFinalizer._publish(ws, "run_completed", run, {}, 3)
    ev = q.get_nowait()
    assert ev["type"] == "coding_run_update"
    assert ev["data"]["mission_id"] == mission.id and ev["data"]["run_id"] == "run-1" and ev["data"]["seq"] == 3
    assert ev["envelope"]["workspace_id"] == ws.id


# --- through the real orchestrator/registry (no direct finalize call) ---------------------------------------------
import stat
from unittest.mock import patch

from aether.coding.models import CodingProviderStatus
from aether.coding.orchestrator import CodingAgentOrchestrator
from aether.coding.providers.claude_code import ClaudeCodeCodingProvider
from aether.coding.runs import CodingRunRegistry


def _orch(tmp_path, body, monkeypatch):
    reg = CodingRunRegistry()
    monkeypatch.setattr("aether.coding.runs._registry", reg)
    monkeypatch.setattr("aether.coding.orchestrator.get_run_registry", lambda: reg)
    script = write_agent_script(tmp_path, "agent", body)
    prov = ClaudeCodeCodingProvider()
    status = CodingProviderStatus(id=prov.id, name=prov.name, description="", installed=True, authenticated=True, available=True, diagnostic="ok")
    ps = [patch.object(prov, "is_available", return_value=(True, "ok")), patch.object(prov, "resolve_binary", return_value=str(script)),
          patch.object(prov, "probe_status", return_value=status)]
    for p in ps:
        p.start()
    return CodingAgentOrchestrator(providers=[prov]), ps


@pytest.mark.parametrize("body,expected", [("echo 'def add(a, b): return a + b' > calc.py", "waiting"), ("exit 3", "failed")])
def test_registry_closes_the_loop_for_real_runs(ctx, tmp_path, monkeypatch, body, expected):
    ws, project, mission = ctx
    orch, ps = _orch(tmp_path, body, monkeypatch)
    try:
        orch.bind_run_store(ws.coding_runs)
        run = orch.delegate_task(CodingTask(instruction="Implement calc.add", project_path=str(project), timeout_seconds=15,
                                            workspace_id=ws.id, mission_id=mission.id))
    finally:
        for p in ps:
            p.stop()
    status, ms = statuses(ws, mission.id)
    assert status == expected, (run.status, run.error)
    assert ms[0] == ("completed" if expected == "waiting" else "failed")


# --- concurrency / late events (block A.1) ---------------------------------------------------------------------------

def _second_run(ws, project, mission_id, status, verified=False, test_run=None):
    run = make_run(ws, project, mission_id, status=status, verified=verified, test_run=test_run)
    run.id = "run-2"
    return run


def test_late_failure_of_another_run_cannot_undo_a_completed_mission(ctx):
    ws, project, mission = ctx
    fin = CodingMissionFinalizer()
    fin.finalize(ws, mission.id, make_run(ws, project, mission.id, test_run={"passed": True, "exit_code": 0, "runner": "pytest"}))
    assert statuses(ws, mission.id)[0] == "completed"
    fin.finalize(ws, mission.id, _second_run(ws, project, mission.id, S.FAILED))        # late event of a different run
    status, ms = statuses(ws, mission.id)
    assert status == "completed" and ms == ["completed", "completed"]
    assert all(d.status == "verified" for d in ws.missions.list_deliverables(mission.id))
    m = ws.missions.get_mission(mission.id)
    assert any(x["run_id"] == "run-2" and x["status"] == "failed" for x in m.metadata["ignored_late_runs"])   # kept as evidence


def test_late_events_of_the_run_that_completed_it_are_idempotent(ctx):
    ws, project, mission = ctx
    fin = CodingMissionFinalizer()
    done = make_run(ws, project, mission.id, test_run={"passed": True, "exit_code": 0, "runner": "pytest"})
    fin.finalize(ws, mission.id, done)
    fin.finalize(ws, mission.id, done)
    assert statuses(ws, mission.id)[0] == "completed"
    assert len(ws.missions.list_executions(mission.id)) == 1


def test_a_failed_mission_can_still_be_completed_by_a_later_verified_run(ctx):
    ws, project, mission = ctx
    fin = CodingMissionFinalizer()
    fin.finalize(ws, mission.id, make_run(ws, project, mission.id, verified=False))
    assert statuses(ws, mission.id)[0] == "failed"
    fin.finalize(ws, mission.id, _second_run(ws, project, mission.id, S.COMPLETED, verified=True,
                                             test_run={"passed": True, "exit_code": 0, "runner": "pytest"}))
    assert statuses(ws, mission.id)[0] == "completed"


def test_two_runs_ending_at_the_same_time_cannot_leave_the_mission_failed(ctx):
    import threading
    ws, project, mission = ctx
    fin = CodingMissionFinalizer()
    good = make_run(ws, project, mission.id, test_run={"passed": True, "exit_code": 0, "runner": "pytest"})
    bad = _second_run(ws, project, mission.id, S.FAILED)
    barrier = threading.Barrier(2)

    def go(run):
        barrier.wait()
        fin.finalize(ws, mission.id, run)

    threads = [threading.Thread(target=go, args=(r,)) for r in (good, bad)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert statuses(ws, mission.id)[0] == "completed"


def test_cancelled_mission_is_not_resurrected_by_a_late_run(ctx):
    ws, project, mission = ctx
    ws.missions.update_mission(mission.id, status="cancelled")
    CodingMissionFinalizer().finalize(ws, mission.id, make_run(ws, project, mission.id, test_run={"passed": True, "exit_code": 0, "runner": "pytest"}))
    assert statuses(ws, mission.id)[0] == "cancelled"
    assert not ws.missions.list_deliverables(mission.id)
