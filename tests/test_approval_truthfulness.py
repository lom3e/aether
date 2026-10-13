"""
The canonical approval answer must say what really happened, derived from the execution state AFTER the call:
approved/executed, still in progress (e.g. a concurrent request is already running it), already completed, failed.
Approving never implies that the action succeeded.

The concurrency test drives the real ``ActionExecutor`` with a controllable handler: no provider, no network.
"""
from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

from aether.actions.models import ActionDefinition, ActionPermissionLevel, ActionTier
from aether.server.app import app
from aether.server.routes import (
    CanonicalApprovalPayload,
    approve_canonical_target_route,
    describe_action_decision_outcome,
    reject_canonical_target_route,
)
from aether.workspace.workspace import Workspace


def _execution(status, output=None, error=None):
    return SimpleNamespace(status=status, output_data=output or {}, error_message=error)


@pytest.mark.parametrize(
    "decision,before,execution,expected_success,expected_status",
    [
        ("approve", "waiting_approval", _execution("succeeded"), True, "approved"),
        ("approve", "succeeded", _execution("succeeded"), True, "already_completed"),
        ("approve", "waiting_approval", _execution("running"), True, "in_progress"),
        ("approve", "running", _execution("running"), True, "in_progress"),  # the concurrent-request case
        ("approve", "waiting_approval", _execution("approved"), True, "in_progress"),
        ("approve", "waiting_approval", _execution("failed", error="boom"), False, "failed"),
        ("approve", "waiting_approval", _execution("waiting_approval"), False, "not_executed"),
        ("reject", "waiting_approval", _execution("rejected"), True, "rejected"),
        ("reject", "rejected", _execution("rejected"), True, "already_completed"),
        ("reject", "waiting_approval", _execution("succeeded"), False, "not_executed"),
    ],
)
def test_outcome_description_follows_the_state_after_the_call(decision, before, execution, expected_success, expected_status):
    success, status, message = describe_action_decision_outcome(decision, before, execution)
    assert (success, status) == (expected_success, expected_status)
    assert message


def test_a_failed_action_is_never_described_as_executed():
    _, _, message = describe_action_decision_outcome("approve", "waiting_approval", _execution("failed", error="no connection"))
    assert "failed" in message and "no connection" in message and "executed." not in message


def test_in_progress_is_never_described_as_completed():
    _, _, message = describe_action_decision_outcome("approve", "running", _execution("running"))
    assert "in progress" in message and "completed yet" in message


def test_a_started_but_unfinished_coding_run_is_not_described_as_done():
    running_run = _execution("succeeded", output={"run_terminal": False, "status": "running"})
    _, status, message = describe_action_decision_outcome("approve", "waiting_approval", running_run)
    assert status == "approved" and "not finished" in message.replace("has not finished", "not finished")
    assert "nothing is verified yet" in message


# --- the route, with the real executor -------------------------------------------------------------------------

def _request():
    return Request({"type": "http", "app": app, "headers": [], "path": "/", "method": "POST"})


class Probe:
    """A controllable action handler: counts executions and can hold the first one until released."""

    def __init__(self, fail: bool = False):
        self.calls = 0
        self.fail = fail
        self.started = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()

    def __call__(self, input_data, workspace_id):
        with self._lock:
            self.calls += 1
        self.started.set()
        if self.fail:
            raise RuntimeError("handler exploded")
        assert self.release.wait(timeout=20), "test bug: the handler was never released"
        return {"done": True}


@pytest.fixture
def pending(tmp_path, accepted_authority_factory):
    ws = Workspace.init(tmp_path / "ws", "Approval Truth WS")
    app.state.workspace = ws  # the autouse reset fixture closes it after the test
    probe_holder = {}

    def make(probe: Probe):
        definition = ActionDefinition(
            id="test.truthful_action",
            name="Truthful test action",
            description="Test-only action requiring approval",
            tier=ActionTier.ACT,
            permission_level=ActionPermissionLevel.LOCAL_MUTATION,
            requires_confirmation=True,
            provider="test",
        )
        ws.action_registry.register(definition, probe)
        _, authority = accepted_authority_factory(ws, title="Truthful action")
        execution = ws.actions.execute("test.truthful_action", ws.id, {"x": 1}, auto_approve=False, authority=authority)
        assert execution.status.value == "waiting_approval"
        probe_holder["id"] = execution.id
        return ws, execution.id

    return make


def _payload(ws):
    return CanonicalApprovalPayload(target_type="action_execution", approver="tester", workspace_id=ws.id)


@pytest.mark.asyncio
async def test_two_concurrent_approvals_execute_once_and_the_second_answer_says_in_progress(pending):
    probe = Probe()
    ws, target = pending(probe)
    first = asyncio.create_task(approve_canonical_target_route(_request(), target_id=target, payload=_payload(ws)))
    assert await asyncio.to_thread(probe.started.wait, 20), "the first approval never reached the handler"

    second = await asyncio.wait_for(
        approve_canonical_target_route(_request(), target_id=target, payload=_payload(ws)), timeout=20
    )
    assert second["status"] == "in_progress" and second["success"] is True
    assert second["entity"]["status"] == "running"
    assert "executed." not in second["message"] and "completed yet" in second["message"]
    assert probe.calls == 1, "a concurrent approval must not run the action again"

    probe.release.set()
    first_result = await asyncio.wait_for(first, timeout=20)
    assert first_result["status"] == "approved" and first_result["entity"]["status"] == "succeeded"
    assert probe.calls == 1

    again = await approve_canonical_target_route(_request(), target_id=target, payload=_payload(ws))
    assert again["status"] == "already_completed" and probe.calls == 1


@pytest.mark.asyncio
async def test_reject_while_the_action_is_running_is_refused_and_does_not_change_the_outcome(pending):
    probe = Probe()
    ws, target = pending(probe)
    first = asyncio.create_task(approve_canonical_target_route(_request(), target_id=target, payload=_payload(ws)))
    assert await asyncio.to_thread(probe.started.wait, 20)

    with pytest.raises(HTTPException) as refused:
        await reject_canonical_target_route(_request(), target_id=target, payload=_payload(ws))
    assert refused.value.status_code == 400

    probe.release.set()
    result = await asyncio.wait_for(first, timeout=20)
    assert result["entity"]["status"] == "succeeded" and probe.calls == 1


@pytest.mark.asyncio
async def test_an_action_that_fails_after_approval_is_reported_as_failed_not_executed(pending):
    probe = Probe(fail=True)
    ws, target = pending(probe)
    result = await approve_canonical_target_route(_request(), target_id=target, payload=_payload(ws))
    assert result["status"] == "failed" and result["success"] is False
    assert result["entity"]["status"] == "failed"
    assert "executed." not in result["message"] and "failed" in result["message"]
    assert probe.calls == 1


@pytest.mark.asyncio
async def test_reject_reports_declined_and_a_second_reject_is_already_completed(pending):
    probe = Probe()
    ws, target = pending(probe)
    declined = await reject_canonical_target_route(_request(), target_id=target, payload=_payload(ws))
    assert declined["status"] == "rejected" and declined["success"] is True and probe.calls == 0
    again = await reject_canonical_target_route(_request(), target_id=target, payload=_payload(ws))
    assert again["status"] == "already_completed" and probe.calls == 0
