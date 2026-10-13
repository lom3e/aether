"""
Durable coding runs: store, recorder, restart recovery, project lock, authorised test execution.
Real SQLite + real child processes of a fake agent script / a project's own unittest files, all in tmp dirs.
"""
from __future__ import annotations

import datetime
import stat
from pathlib import Path
from unittest.mock import patch

import pytest
from fake_agent_script import write_agent_script

from aether.actions.executor import ActionExecutor, ActionSafetyPolicy
from aether.actions.models import ActionExecutionStatus
from aether.actions.registry import ActionRegistry
from aether.actions.store import ActionStore
from aether.coding.models import CodingExecutionStatus as S, CodingProviderStatus, CodingTask
from aether.coding.orchestrator import CodingAgentOrchestrator
from aether.coding.providers.antigravity import AntigravityCodingProvider
from aether.coding.providers.claude_code import ClaudeCodeCodingProvider
from aether.coding.runs import CodingRunRegistry, CodingRunStore, ProjectBusyError, run_authorised_tests
from aether.core.execution import ExecutionAuthority, UnauthorizedExecutionError
from aether.planning.contracts import ProposalStatus

WS = "ws-runs"


@pytest.fixture
def registry(monkeypatch):
    reg = CodingRunRegistry()
    monkeypatch.setattr("aether.coding.runs._registry", reg)
    monkeypatch.setattr("aether.coding.orchestrator.get_run_registry", lambda: reg)
    return reg


def make_agent(tmp_path, body):
    return write_agent_script(tmp_path, "agent", body)


def orchestrator_for(provider, agent):
    status = CodingProviderStatus(id=provider.id, name=provider.name, description="", installed=True,
                                  authenticated=True, available=True, diagnostic="ok")
    patches = [patch.object(provider, "is_available", return_value=(True, "ok")),
               patch.object(provider, "resolve_binary", return_value=agent),
               patch.object(provider, "probe_status", return_value=status)]
    for p in patches:
        p.start()
    return CodingAgentOrchestrator(providers=[provider]), patches


@pytest.fixture
def env(tmp_path, registry):
    project = tmp_path / "proj"
    project.mkdir()
    store = CodingRunStore(tmp_path / "coding_runs.db", WS)
    started = []
    yield tmp_path, project, store, started
    for p in started:
        p.stop()


def delegate(orch, project, instruction="Crea un file", **kw):
    return orch.delegate_task(CodingTask(instruction=instruction, project_path=str(project), timeout_seconds=10,
                                         workspace_id=WS, mission_id="m-1", proposal_id="p-1", **kw))


def test_run_state_events_and_baseline_are_persisted(env):
    tmp_path, project, store, started = env
    prov = ClaudeCodeCodingProvider()
    orch, ps = orchestrator_for(prov, make_agent(tmp_path, "echo hi > out.py"))
    started += ps
    orch.bind_run_store(store)
    ex = delegate(orch, project)
    saved = store.get_run(ex.id)
    assert saved.status == S.COMPLETED and saved.result.modified_files == ["out.py"]
    assert [e["event"] for e in store.list_events(run_id=ex.id)] == ["run_started", "run_completed"]
    assert store.list_events(mission_id="m-1")[0]["provider_id"] == "claude_code"
    assert store.load_baseline(ex.id) is not None
    assert store.list_runs(mission_id="m-1")[0].id == ex.id


def test_other_workspace_cannot_see_the_run(env, tmp_path):
    _, project, store, started = env
    other = CodingRunStore(tmp_path / "other.db", "ws-other")
    prov = ClaudeCodeCodingProvider()
    orch, ps = orchestrator_for(prov, make_agent(tmp_path, "true"))
    started += ps
    orch.bind_run_store(store)
    ex = delegate(orch, project)
    assert other.get_run(ex.id) is None and other.list_runs() == []


def test_waiting_run_survives_restart_and_running_run_is_failed_explicitly(env):
    tmp_path, project, store, started = env
    prov = AntigravityCodingProvider()
    orch, ps = orchestrator_for(prov, "/fake/agentapi")
    started += ps
    orch.bind_run_store(store)
    from aether.coding.models import CodingTaskExecution
    waiting = CodingTaskExecution(id="exec-wait", task=CodingTask(instruction="x", project_path=str(project), workspace_id=WS, mission_id="m-9"),
                                  provider_id="antigravity", status=S.WAITING_FOR_INTERACTION, external_task_id="conv-wait-1")
    running = CodingTaskExecution(id="exec-run", task=CodingTask(instruction="y", project_path=str(project), workspace_id=WS),
                                  provider_id="antigravity", status=S.RUNNING, external_task_id="conv-run-1")
    for e in (waiting, running):
        store.save_run(e)

    # "restart": brand-new orchestrator + provider objects, same database
    prov2 = AntigravityCodingProvider()
    orch2, ps2 = orchestrator_for(prov2, "/fake/agentapi")
    started += ps2
    touched = orch2.bind_run_store(store) and orch2.recover_runs(store)
    assert set(orch2._executions) == {"exec-wait"}
    assert orch2.get_status("exec-wait").status == S.WAITING_FOR_INTERACTION
    assert prov2.get_status("exec-wait").external_task_id == "conv-wait-1"

    failed = store.get_run("exec-run")
    assert failed.status == S.FAILED and failed.metadata["interrupted_by_restart"] is True
    assert failed.metadata["remote_session_may_continue"] is True
    assert "restarted" in failed.error
    assert any(e["event"] == "run_interrupted_by_restart" for e in store.list_events(run_id="exec-run"))


def test_runs_are_found_lazily_from_the_store_after_restart(env):
    tmp_path, project, store, started = env
    prov = ClaudeCodeCodingProvider()
    orch, ps = orchestrator_for(prov, make_agent(tmp_path, "echo x > f.py"))
    started += ps
    orch.bind_run_store(store)
    ex = delegate(orch, project)
    prov2 = ClaudeCodeCodingProvider()
    orch2, ps2 = orchestrator_for(prov2, "/none")
    started += ps2
    orch2.bind_run_store(store)
    assert orch2.get_status(ex.id).status == S.COMPLETED
    assert orch2.collect_results(ex.id).modified_files == ["f.py"]  # baseline restored too


def test_second_task_on_a_busy_project_is_refused_until_the_first_is_done(env):
    tmp_path, project, store, started = env
    prov = AntigravityCodingProvider()
    orch, ps = orchestrator_for(prov, "/fake/agentapi")
    started += ps
    orch.bind_run_store(store)
    from aether.coding.models import CodingTaskExecution
    store.save_run(CodingTaskExecution(id="exec-live", task=CodingTask(instruction="x", project_path=str(project), workspace_id=WS),
                                       provider_id="antigravity", status=S.WAITING_FOR_INTERACTION))
    with pytest.raises(ProjectBusyError) as e:
        delegate(orch, project)
    assert "exec-live" in str(e.value)
    # a different project is unaffected
    other = tmp_path / "other_proj"; other.mkdir()
    prov2 = ClaudeCodeCodingProvider()
    orch2, ps2 = orchestrator_for(prov2, make_agent(tmp_path, "true"))
    started += ps2
    orch2.bind_run_store(store)
    assert delegate(orch2, other, instruction="Analizza il progetto").status == S.COMPLETED


def test_timed_out_remote_session_keeps_the_project_locked_until_observed_idle_or_released(env):
    tmp_path, project, store, started = env
    prov = AntigravityCodingProvider()
    orch, ps = orchestrator_for(prov, "/fake/agentapi")
    started += ps
    orch.bind_run_store(store)
    from aether.coding.models import CodingTaskExecution
    ex = CodingTaskExecution(id="exec-to", task=CodingTask(instruction="x", project_path=str(project), workspace_id=WS),
                             provider_id="antigravity", status=S.TIMED_OUT, external_task_id="conv-to-1")
    ex.metadata["remote_session_may_continue"] = True
    store.save_run(ex)
    with patch.object(prov, "remote_activity_state", return_value="active"):
        with pytest.raises(ProjectBusyError):
            delegate(orch, project)
    # explicit human release unlocks it
    assert store.mark_released("exec-to", "confirmed stopped in Antigravity UI")
    prov3 = ClaudeCodeCodingProvider()
    orch3, ps3 = orchestrator_for(prov3, make_agent(tmp_path, "true"))
    started += ps3
    orch3.bind_run_store(store)
    assert delegate(orch3, project, instruction="Analizza il progetto").status == S.COMPLETED


def test_remote_idle_observation_releases_automatically(env):
    tmp_path, project, store, started = env
    prov = AntigravityCodingProvider()
    orch, ps = orchestrator_for(prov, "/fake/agentapi")
    started += ps
    orch.bind_run_store(store)
    from aether.coding.models import CodingTaskExecution
    ex = CodingTaskExecution(id="exec-idle", task=CodingTask(instruction="x", project_path=str(project), workspace_id=WS),
                             provider_id="antigravity", status=S.CANCELLED, external_task_id="conv-idle-1")
    ex.metadata["remote_session_may_continue"] = True
    store.save_run(ex)
    registry_providers = {"antigravity": prov}
    from aether.coding.runs import get_run_registry
    with patch.object(prov, "remote_activity_state", return_value="idle"):
        get_run_registry().assert_project_free(str(project), registry_providers)  # no raise
    assert store.get_run("exec-idle").metadata["remote_released"] is True


# --- authorised test execution ------------------------------------------------------

def make_project(tmp_path, passing=True):
    p = tmp_path / ("good" if passing else "bad")
    p.mkdir()
    (p / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    expected = "3" if passing else "4"
    (p / "test_calc.py").write_text(
        "import os, unittest\nfrom calc import add\n\nclass T(unittest.TestCase):\n"
        f"    def test_add(self):\n        self.assertEqual(add(1, 2), {expected})\n"
        "    def test_no_inherited_secrets(self):\n        self.assertNotIn('GROQ_API_KEY', os.environ)\n",
        encoding="utf-8")
    return p


def fake_run(project):
    from aether.coding.models import CodingTaskExecution
    return CodingTaskExecution(id="exec-t", task=CodingTask(instruction="x", project_path=str(project)), provider_id="claude_code",
                               status=S.COMPLETED)


def test_authorised_tests_report_real_exit_code_and_scrub_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "should-not-leak")
    good = run_authorised_tests(fake_run(make_project(tmp_path, True)), runner="unittest", timeout_seconds=60)
    assert good["passed"] is True and good["exit_code"] == 0 and "OK" in good["output"]
    bad = run_authorised_tests(fake_run(make_project(tmp_path, False)), runner="unittest", timeout_seconds=60)
    assert bad["passed"] is False and bad["exit_code"] != 0 and "FAILED" in bad["output"]


def test_runner_is_whitelisted_and_timeout_kills_the_group(tmp_path):
    with pytest.raises(ValueError):
        run_authorised_tests(fake_run(make_project(tmp_path)), runner="rm -rf /")
    slow = tmp_path / "slow"; slow.mkdir()
    (slow / "test_slow.py").write_text("import time, unittest\nclass T(unittest.TestCase):\n    def test_s(self):\n        time.sleep(30)\n", encoding="utf-8")
    out = run_authorised_tests(fake_run(slow), runner="unittest", timeout_seconds=1)
    assert out["timed_out"] is True and out["passed"] is False and out["duration_seconds"] < 10


# --- through the action layer: authority + sensitive approval + ownership -------------

class FakePStore:
    def __init__(self, constraints):
        self.p = type("P", (), {"id": "prop-1", "version": 1, "workspace_id": WS, "status": ProposalStatus.ACCEPTED,
                                 "constraints": constraints, "executed_steps": []})()
        self.steps = []
    def get_proposal(self, pid, workspace_id=None): return self.p if pid == "prop-1" else None
    def is_step_executed(self, pid, s): return s in self.steps
    def is_action_executed(self, *a, **k): return False
    def list_executed_steps(self, pid): return list(self.steps)
    def record_step_executed(self, proposal_id, step_id, action_id="", args_digest=""): self.steps.append(step_id)


def test_run_tests_action_needs_authority_human_approval_and_ownership(env, tmp_path, registry):
    _, project, store, started = env
    good = make_project(tmp_path, True)
    prov = ClaudeCodeCodingProvider()
    orch, ps = orchestrator_for(prov, make_agent(tmp_path, "true"))
    started += ps
    executor = ActionExecutor(registry=ActionRegistry(), store=ActionStore(str(tmp_path / "actions.db")),
                              personal_store=FakePStore([f"allow:coding.delegate", f"allow_path:{good}"]),
                              safety_policy=ActionSafetyPolicy())
    with patch("aether.coding.orchestrator.get_coding_orchestrator", return_value=orch):
        run_store = executor._coding_run_store(WS)
        orch.bind_run_store(run_store)
        run = orch.delegate_task(CodingTask(instruction="Analizza", project_path=str(good), timeout_seconds=10,
                                            workspace_id=WS, proposal_id="prop-1"))
        auth = ExecutionAuthority(proposal_id="prop-1", proposal_version=1, workspace_id=WS,
                                  granted_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        # no authority -> refused
        with pytest.raises(UnauthorizedExecutionError):
            executor.execute("coding.run_tests", WS, {"execution_id": run.id})
        # authority of another proposal -> refused (ownership)
        other = ExecutionAuthority(proposal_id="prop-x", proposal_version=1, workspace_id=WS, granted_at=auth.granted_at)
        with pytest.raises(UnauthorizedExecutionError):
            executor.execute("coding.run_tests", WS, {"execution_id": run.id}, authority=other)
        # right authority: still needs explicit human approval (sensitive mutation), tests have NOT run yet
        queued = executor.execute("coding.run_tests", WS, {"execution_id": run.id, "runner": "unittest"}, authority=auth, auto_approve=True)
        assert queued.status == ActionExecutionStatus.WAITING_APPROVAL
        assert "test_run" not in run_store.get_run(run.id).metadata
        done = executor.approve(queued.id, approver="user")
        assert done.status == ActionExecutionStatus.SUCCEEDED
        assert done.output_data["passed"] is True and done.output_data["exit_code"] == 0
        saved = run_store.get_run(run.id)
        assert saved.metadata["test_run"]["passed"] is True
        assert [e["event"] for e in run_store.list_events(run_id=run.id)][-1] == "tests_run"
