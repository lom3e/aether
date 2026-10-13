"""
Phase 1: policy decisions, approval-time re-evaluation, authority perimeter, consent, and the coding
interaction endpoint. Isolated: temp SQLite files, a fake orchestrator, no processes, no network.
"""
from __future__ import annotations

import asyncio
import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from aether.actions.executor import ActionExecutor, ActionSafetyPolicy
from aether.actions.models import (
    ActionDefinition, ActionExecution, ActionExecutionStatus, ActionPermissionLevel, ActionTier,
)
from aether.actions.registry import ActionRegistry
from aether.actions.store import ActionStore
from aether.coding.models import CodingExecutionStatus, CodingTask, CodingTaskExecution
from aether.core.execution import ExecutionAuthority, UnauthorizedExecutionError, _workspaces_match
from aether.planning.contracts import ProposalStatus
from aether.policy import PolicyDecision, PolicyOutcome, PolicyService, PolicyStore

WS = "ws-test"


class FakeProposal:
    def __init__(self, pid="prop-1", ws=WS, constraints=None, status=ProposalStatus.ACCEPTED):
        self.id, self.version, self.workspace_id = pid, 1, ws
        self.status = status
        self.constraints = constraints if constraints is not None else ["allow:coding.delegate"]
        self.executed_steps: list[str] = []


class FakePStore:
    def __init__(self, proposal):
        self.proposal = proposal
        self.steps: list[str] = []

    def get_proposal(self, pid, workspace_id=None):
        return self.proposal if self.proposal.id == pid else None

    def is_step_executed(self, pid, step):
        return step in self.steps

    def is_action_executed(self, *a, **k):
        return False

    def list_executed_steps(self, pid):
        return list(self.steps)

    def record_step_executed(self, proposal_id, step_id, action_id="", args_digest=""):
        if step_id in self.steps:
            raise ValueError("replay")
        self.steps.append(step_id)


def now_plus(hours=1):
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=hours)).isoformat()


def authority(pid="prop-1", ws=WS, **kw):
    return ExecutionAuthority(
        proposal_id=pid, proposal_version=1, workspace_id=ws,
        granted_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), expires_at=now_plus(), **kw,
    )


def build(tmp_path, tier="supervised", prohibited=(), constraints=None, register_probe=True):
    registry = ActionRegistry()
    calls: list[dict] = []
    if register_probe:
        registry.register(
            ActionDefinition(
                id="probe.mutate", name="Probe", description="probe", tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.EXTERNAL_MUTATION, requires_confirmation=True,
            ),
            handler=lambda inp, ws: calls.append(inp) or {"ok": True},
        )
    policy = PolicyService(PolicyStore(tmp_path / "policies.db"))
    policy.update_policy(WS, {"autopilot_tier": tier, "prohibited_actions": list(prohibited)})
    proposal = FakeProposal(constraints=constraints if constraints is not None else ["allow:probe.mutate", "allow:coding.delegate"])
    pstore = FakePStore(proposal)
    executor = ActionExecutor(
        registry=registry, store=ActionStore(db_path=str(tmp_path / "actions.db")),
        personal_store=pstore, safety_policy=ActionSafetyPolicy(policy_service=policy),
    )
    return executor, policy, pstore, calls


# --- typed policy decisions ---------------------------------------------------

def test_policy_decisions_have_stable_codes_and_legacy_tuple_still_works(tmp_path):
    _, policy, *_ = build(tmp_path, tier="manual", prohibited=["probe.mutate"])
    kw = dict(workspace_id=WS, permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
              requires_confirmation=True, auto_approve_requested=True)
    d = policy.evaluate_action_decision(action_id="probe.mutate", **kw)
    assert (d.outcome, d.code) == (PolicyOutcome.DENY, "ACTION_PROHIBITED")
    d2 = policy.evaluate_action_decision(action_id="other.thing", **kw)
    assert (d2.outcome, d2.code) == (PolicyOutcome.NEEDS_APPROVAL, "TIER_MANUAL")
    assert policy.evaluate_action(action_id="other.thing", **kw)[0] is False


def test_denial_is_recognised_by_code_not_by_wording(tmp_path):
    executor, policy, pstore, calls = build(tmp_path)
    reworded = PolicyDecision(PolicyOutcome.DENY, "COMPLIANCE_BLOCK", "Blocked: not permitted here.")  # no magic word
    with patch.object(policy, "evaluate_action_decision", return_value=reworded):
        ex = executor.execute("probe.mutate", WS, {"x": 1}, authority=authority(), auto_approve=True)
    assert ex.status == ActionExecutionStatus.FAILED
    assert ex.metadata["policy_code"] == "COMPLIANCE_BLOCK"
    assert calls == []


def test_needs_approval_wording_containing_prohibited_is_not_a_denial(tmp_path):
    executor, policy, pstore, calls = build(tmp_path)
    hold = PolicyDecision(PolicyOutcome.NEEDS_APPROVAL, "TIER_MANUAL", "Nothing is prohibited, a human must confirm.")
    with patch.object(policy, "evaluate_action_decision", return_value=hold):
        ex = executor.execute("probe.mutate", WS, {"x": 1}, authority=authority(), auto_approve=True)
    assert ex.status == ActionExecutionStatus.WAITING_APPROVAL


# --- policy re-evaluated at approval -------------------------------------------

def test_policy_is_reevaluated_when_a_waiting_action_is_approved(tmp_path):
    executor, policy, pstore, calls = build(tmp_path, tier="manual")
    queued = executor.execute("probe.mutate", WS, {"x": 1}, authority=authority())
    assert queued.status == ActionExecutionStatus.WAITING_APPROVAL

    policy.update_policy(WS, {"prohibited_actions": ["probe.mutate"]})  # admin forbids it while it waits
    result = executor.approve(queued.id, approver="someone")

    assert result.status == ActionExecutionStatus.FAILED
    assert result.metadata["policy_code"] == "ACTION_PROHIBITED"
    assert calls == [], "a denied action must never reach its handler"


def test_human_approval_still_satisfies_needs_approval(tmp_path):
    executor, policy, pstore, calls = build(tmp_path, tier="manual")
    queued = executor.execute("probe.mutate", WS, {"x": 1}, authority=authority())
    done = executor.approve(queued.id, approver="user")
    assert done.status == ActionExecutionStatus.SUCCEEDED and calls == [{"x": 1}]


def test_autonomous_tier_still_runs_when_policy_allows(tmp_path):
    executor, policy, pstore, calls = build(tmp_path, tier="autonomous")
    ex = executor.execute("probe.mutate", WS, {"x": 1}, authority=authority(), auto_approve=True)
    assert ex.status == ActionExecutionStatus.SUCCEEDED and calls == [{"x": 1}]


# --- consent is structured, never data -----------------------------------------

def test_auto_approve_key_inside_action_data_is_discarded(tmp_path):
    executor, policy, pstore, calls = build(tmp_path, tier="supervised")
    ex = executor.execute("probe.mutate", WS, {"x": 1, "auto_approve": True}, authority=authority())
    assert ex.status == ActionExecutionStatus.WAITING_APPROVAL
    assert "auto_approve" not in ex.input_data


def test_runtime_ignores_auto_approve_smuggled_in_action_args():
    from aether.core.execution import Task
    from aether.core.runtime import Runtime
    fake_exec = MagicMock()
    fake_exec.registry.get.return_value = SimpleNamespace(name="Probe")
    fake_exec.execute.return_value = SimpleNamespace(
        status=ActionExecutionStatus.WAITING_APPROVAL, id="ax-1", output_data={}, error_message=None, metadata={})
    rt = Runtime(action_executor=fake_exec)
    rt._execute_act(Task(instruction="x", action_id="probe.mutate", action_args={"auto_approve": True}, authority=authority()))
    kwargs = fake_exec.execute.call_args.kwargs
    assert kwargs["auto_approve"] is False
    assert "auto_approve" not in kwargs["input_data"]
    # structured consent without authority is also not honoured
    rt._execute_act(Task(instruction="x", action_id="probe.mutate", auto_approve=True, authority=None))
    assert fake_exec.execute.call_args.kwargs["auto_approve"] is False


# --- authority scope: workspace, operation, perimeter ---------------------------

def test_workspace_identity_is_not_matched_loosely():
    assert _workspaces_match("ws-a", "ws-a")
    assert not _workspaces_match("ws-a", "ws-b")
    assert not _workspaces_match("", "ws-a")
    assert not _workspaces_match("default", "unknown-workspace-name")


def test_authority_for_another_workspace_is_rejected(tmp_path):
    executor, *_ = build(tmp_path)
    with pytest.raises(UnauthorizedExecutionError):
        executor.execute("probe.mutate", WS, {"x": 1}, authority=authority(ws="ws-other"))


def test_allow_path_perimeter_is_enforced_for_coding_delegation(tmp_path):
    project = tmp_path / "proj"; project.mkdir()
    outside = tmp_path / "outside"; outside.mkdir()
    cons = ["allow:coding.delegate", f"allow_path:{project}"]
    executor, *_ = build(tmp_path, constraints=cons)
    for bad in ({"instruction": "x", "project_path": str(outside)}, {"instruction": "x"},
                {"instruction": "x", "project_path": str(project), "context_files": ["../outside/a.py"]}):
        with pytest.raises(UnauthorizedExecutionError):
            executor.execute("coding.delegate", WS, bad, authority=authority())


def test_coding_delegate_refuses_aether_installation_and_home_without_explicit_allow(tmp_path):
    from pathlib import Path
    import aether
    repo_root = Path(aether.__file__).resolve().parents[2]
    with pytest.raises(UnauthorizedExecutionError):  # not authorised at all
        ActionExecutor._assert_coding_path_allowed(repo_root, [], [])
    with pytest.raises(ValueError):  # even as "the workspace root", the Aether installation needs an explicit allow_path
        ActionExecutor._assert_coding_path_allowed(repo_root, [], [repo_root])
    with pytest.raises(ValueError):
        ActionExecutor._assert_coding_path_allowed(Path.home().resolve(), [])
    # positive perimeter: an ordinary directory is refused unless the proposal names it or it is the workspace
    with pytest.raises(UnauthorizedExecutionError):
        ActionExecutor._assert_coding_path_allowed(tmp_path, [], [])
    ActionExecutor._assert_coding_path_allowed(tmp_path, [str(tmp_path)], [])
    ActionExecutor._assert_coding_path_allowed(tmp_path / "sub", [], [tmp_path])
    ActionExecutor._assert_coding_path_allowed(repo_root, [str(repo_root)], [])  # explicit perimeter permits it


# --- /personal/coding/interact --------------------------------------------------

class FakeOrchestrator:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []
        self._executions = {"exec-run1": (None, None)}

    def bind_run_store(self, store):
        return store

    def _find(self, exec_id):
        return self._executions.get(exec_id)

    def send_message(self, exec_id, message):
        self.sent.append((exec_id, message))
        task = CodingTask(instruction="i", project_path="/tmp/x")
        return CodingTaskExecution(id=exec_id, task=task, provider_id="antigravity", status=CodingExecutionStatus.RUNNING)


def seed_run(executor, ws=WS, proposal_id="prop-1", with_authority=True):
    meta = {"coding_execution_id": "exec-run1"}
    if with_authority:
        meta["authority"] = authority(pid=proposal_id, ws=ws).to_dict()
    rec = ActionExecution(
        id="ax-delegate", action_id="coding.delegate", workspace_id=ws, provider="coding",
        input_data={"instruction": "do"}, metadata=meta,
    )
    rec.status = ActionExecutionStatus.SUCCEEDED
    rec.output_data = {"execution_id": "exec-run1"}
    executor.store.save_execution(rec)


def call_route(executor, **payload):
    from aether.server.routes import CodingInteractPayload, coding_interact_route
    ws = SimpleNamespace(name=WS, actions=executor)
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(workspace=ws)))
    return asyncio.run(coding_interact_route(req, CodingInteractPayload(**payload)))


@pytest.fixture
def orch():
    fake = FakeOrchestrator()
    with patch("aether.coding.orchestrator.get_coding_orchestrator", return_value=fake):
        yield fake


def test_interact_valid_run_goes_through_executor_and_is_recorded(tmp_path, orch):
    executor, policy, pstore, _ = build(tmp_path, tier="supervised")
    seed_run(executor)
    out = call_route(executor, execution_id="exec-run1", message="Approva ed esegui modifiche")
    assert out["status"] == "sent" and orch.sent == [("exec-run1", "Approva ed esegui modifiche")]
    rec = executor.store.get_execution(out["action_execution_id"])
    assert rec.action_id == "coding.interact" and rec.approved_by == "session_user"
    assert rec.metadata["authority"]["proposal_id"] == "prop-1"


def test_interact_twice_is_not_blocked_as_a_replay(tmp_path, orch):
    executor, *_ = build(tmp_path)
    seed_run(executor)
    call_route(executor, execution_id="exec-run1", message="one")
    call_route(executor, execution_id="exec-run1", message="two")
    assert [m for _, m in orch.sent] == ["one", "two"]


def test_interact_unknown_run_or_other_workspace_is_404(tmp_path, orch):
    executor, *_ = build(tmp_path)
    with pytest.raises(HTTPException) as e1:
        call_route(executor, execution_id="exec-run1", message="hi")
    assert e1.value.status_code == 404
    seed_run(executor, ws="ws-other")
    with pytest.raises(HTTPException) as e2:
        call_route(executor, execution_id="exec-run1", message="hi")
    assert e2.value.status_code == 404 and orch.sent == []


def test_interact_without_authority_is_refused(tmp_path, orch):
    executor, *_ = build(tmp_path)
    seed_run(executor, with_authority=False)
    with pytest.raises(HTTPException) as e:
        call_route(executor, execution_id="exec-run1", message="go")
    assert e.value.status_code == 403 and orch.sent == []


def test_interact_with_revoked_proposal_is_refused(tmp_path, orch):
    executor, policy, pstore, _ = build(tmp_path)
    seed_run(executor)
    pstore.proposal.status = ProposalStatus.REVOKED if hasattr(ProposalStatus, "REVOKED") else ProposalStatus.DRAFT
    with pytest.raises(HTTPException) as e:
        call_route(executor, execution_id="exec-run1", message="go")
    assert e.value.status_code == 403 and orch.sent == []


def test_interact_denied_by_policy_even_with_valid_authority(tmp_path, orch):
    executor, *_ = build(tmp_path, prohibited=["coding.interact"])
    seed_run(executor)
    with pytest.raises(HTTPException) as e:
        call_route(executor, execution_id="exec-run1", message="go")
    assert e.value.status_code == 403 and e.value.detail["policy_code"] == "ACTION_PROHIBITED"
    assert orch.sent == []


def test_interact_blocked_when_delegation_itself_is_prohibited(tmp_path, orch):
    executor, *_ = build(tmp_path, prohibited=["coding.delegate"])
    seed_run(executor)
    with pytest.raises(HTTPException) as e:
        call_route(executor, execution_id="exec-run1", message="go")
    assert e.value.status_code == 403 and orch.sent == []


def test_interact_with_authority_of_a_different_proposal_is_refused(tmp_path, orch):
    executor, policy, pstore, _ = build(tmp_path)
    seed_run(executor)
    # a valid authority for ANOTHER proposal must not be usable on this run
    other = authority(pid="prop-other")
    with pytest.raises(UnauthorizedExecutionError):
        executor.execute("coding.interact", WS, {"execution_id": "exec-run1", "message": "x"}, authority=other)
    assert orch.sent == []


# --- authentication fail-closed -------------------------------------------------

def _request(path, host="127.0.0.1"):
    from starlette.requests import Request
    from aether.server.app import app
    return Request({"type": "http", "method": "POST", "path": path, "headers": [], "query_string": b"",
                    "client": (host, 5000), "app": app})


def _run_middleware(path, host="127.0.0.1"):
    from aether.server.app import app, session_token_middleware
    app.state.session_token = None

    async def ok(_):
        return SimpleNamespace(status_code=200)
    return asyncio.run(session_token_middleware(_request(path, host), ok))


def test_sensitive_routes_fail_closed_without_token_and_without_dev_flag(monkeypatch):
    monkeypatch.delenv("AETHER_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("AETHER_INSECURE_LOCAL_DEV", raising=False)
    for path in ("/api/personal/coding/interact", "/api/actions/executions/ax-1/approve", "/api/approvals/x/approve"):
        assert _run_middleware(path).status_code == 401
    assert _run_middleware("/api/health").status_code == 200  # non-sensitive routes unchanged


def test_dev_mode_is_explicit_and_loopback_only(monkeypatch):
    monkeypatch.delenv("AETHER_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("AETHER_INSECURE_LOCAL_DEV", "1")
    assert _run_middleware("/api/personal/coding/interact", "127.0.0.1").status_code == 200
    assert _run_middleware("/api/personal/coding/interact", "192.168.1.20").status_code == 401


def test_token_still_required_when_configured(monkeypatch):
    from aether.server.app import app, session_token_middleware
    monkeypatch.setenv("AETHER_INSECURE_LOCAL_DEV", "1")
    app.state.session_token = "tok-123"
    try:
        async def ok(_):
            return SimpleNamespace(status_code=200)
        r = asyncio.run(session_token_middleware(_request("/api/personal/coding/interact"), ok))
        assert r.status_code == 401
    finally:
        app.state.session_token = None
