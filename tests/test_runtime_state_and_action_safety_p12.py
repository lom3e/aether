"""
Unit & Integration tests for Macro-pass P1.2 — Runtime State e Action Safety.
Validates:
- Canonical ActionExecutionStatus state machine transitions.
- Illegal transition prevention from terminal states.
- Truthful failure propagation (no false success fallbacks).
- Idempotency of approve and reject actions.
- Auto-approval audit trail (auto_approved flag and safety_policy approver).
- Deliverable on-disk existence verification before approval.
- Personal agent truthful step reporting and notification suppression on failure.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Any
from unittest.mock import MagicMock, patch
import pytest

from fastapi import HTTPException
from fastapi.requests import Request

from aether.actions.executor import ActionExecutor, ActionSafetyPolicy
from aether.actions.models import (
    ActionDefinition,
    ActionExecution,
    ActionExecutionStatus,
    ActionPermissionLevel,
    VALID_ACTION_TRANSITIONS,
)
from aether.activity.models import ActivityCategory, ActivityStatus
from aether.core.execution import ExecutionMode, ExecutionResult, ExecutionStatus, Task
from aether.core.runtime import Runtime
from aether.missions.models import Deliverable
from aether.notifications.models import NotificationType
from aether.personal.models import IntentTier, PersonalStep, UserIntent
from aether.personal.service import PersonalAgentService
from aether.server.app import app
from aether.server.routes import (
    CanonicalApprovalPayload,
    _handle_canonical_approval,
)
from aether.workspace.workspace import Workspace


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Workspace.init(Path(tmp_dir), name="p12_ws")
        app.state.workspace = ws
        yield ws
        ws.close()


def make_request(method: str = "POST", path: str = "/") -> Request:
    scope = {"type": "http", "app": app, "headers": [], "path": path, "method": method}
    return Request(scope)


# ---------------------------------------------------------------------------
# 1. State Machine & Status Canonicals
# ---------------------------------------------------------------------------

def test_canonical_action_execution_statuses():
    """Verify canonical statuses, values, and backward compatibility aliases."""
    assert ActionExecutionStatus.QUEUED.value == "queued"
    assert ActionExecutionStatus.RUNNING.value == "running"
    assert ActionExecutionStatus.WAITING_APPROVAL.value == "waiting_approval"
    assert ActionExecutionStatus.APPROVED.value == "approved"
    assert ActionExecutionStatus.SUCCEEDED.value == "succeeded"
    assert ActionExecutionStatus.FAILED.value == "failed"
    assert ActionExecutionStatus.REJECTED.value == "rejected"
    assert ActionExecutionStatus.EXPIRED.value == "expired"
    assert ActionExecutionStatus.CANCELLED.value == "cancelled"

    # Backward compatibility equality
    assert ActionExecutionStatus.WAITING_APPROVAL == "pending_approval"
    assert ActionExecutionStatus.WAITING_APPROVAL == "waiting_approval"
    assert ActionExecutionStatus.SUCCEEDED == "success"
    assert ActionExecutionStatus.SUCCEEDED == "succeeded"
    assert ActionExecutionStatus.SUCCEEDED == "completed"

    # from_str parsing
    assert ActionExecutionStatus.from_str("pending_approval") == ActionExecutionStatus.WAITING_APPROVAL
    assert ActionExecutionStatus.from_str("waiting_approval") == ActionExecutionStatus.WAITING_APPROVAL
    assert ActionExecutionStatus.from_str("success") == ActionExecutionStatus.SUCCEEDED
    assert ActionExecutionStatus.from_str("succeeded") == ActionExecutionStatus.SUCCEEDED
    assert ActionExecutionStatus.from_str("completed") == ActionExecutionStatus.SUCCEEDED

    with pytest.raises(ValueError):
        ActionExecutionStatus.from_str("invalid_nonexistent_status")


def test_action_execution_transition_enforcement():
    """Verify legal transitions succeed and illegal transitions raise ValueError."""
    execution = ActionExecution(
        id="ax-sm-01",
        action_id="test.act",
        workspace_id="p12_ws",
        status=ActionExecutionStatus.QUEUED,
    )

    # QUEUED -> RUNNING
    execution.transition_to(ActionExecutionStatus.RUNNING)
    assert execution.status == ActionExecutionStatus.RUNNING

    # RUNNING -> WAITING_APPROVAL
    execution.transition_to(ActionExecutionStatus.WAITING_APPROVAL)
    assert execution.status == ActionExecutionStatus.WAITING_APPROVAL

    # WAITING_APPROVAL -> APPROVED
    execution.transition_to(ActionExecutionStatus.APPROVED)
    assert execution.status == ActionExecutionStatus.APPROVED

    # APPROVED -> RUNNING -> SUCCEEDED
    execution.transition_to(ActionExecutionStatus.RUNNING)
    execution.transition_to(ActionExecutionStatus.SUCCEEDED)
    assert execution.status == ActionExecutionStatus.SUCCEEDED
    assert execution.is_terminal() is True

    # Cannot transition from terminal SUCCEEDED to RUNNING or WAITING_APPROVAL
    with pytest.raises(ValueError, match="Illegal execution transition"):
        execution.transition_to(ActionExecutionStatus.RUNNING)

    with pytest.raises(ValueError, match="Illegal execution transition"):
        execution.transition_to(ActionExecutionStatus.WAITING_APPROVAL)


def test_terminal_states_immutable(temp_workspace):
    """Verify that once in FAILED or REJECTED state, no further transitions are allowed."""
    exec_failed = ActionExecution(
        id="ax-sm-02",
        action_id="test.act",
        workspace_id="p12_ws",
        status=ActionExecutionStatus.FAILED,
    )
    assert exec_failed.is_terminal() is True

    with pytest.raises(ValueError, match="Illegal execution transition"):
        exec_failed.transition_to(ActionExecutionStatus.SUCCEEDED)

    exec_rejected = ActionExecution(
        id="ax-sm-03",
        action_id="test.act",
        workspace_id="p12_ws",
        status=ActionExecutionStatus.REJECTED,
    )
    assert exec_rejected.is_terminal() is True

    with pytest.raises(ValueError, match="Illegal execution transition"):
        exec_rejected.transition_to(ActionExecutionStatus.APPROVED)


# ---------------------------------------------------------------------------
# 2. ActionExecutor Safety, Truthfulness, and Idempotency
# ---------------------------------------------------------------------------

def test_action_executor_auto_approval_audit_trail(temp_workspace):
    """Safe actions auto-approved must record auto_approved=True and approved_by='safety_policy'."""
    executor = temp_workspace.actions

    execution = executor.execute(
        action_id="files.create_document",
        workspace_id="p12_ws",
        input_data={"filename": "notes.md", "content": "hello world"},
        auto_approve=True,
    )
    assert execution.status == ActionExecutionStatus.SUCCEEDED
    assert execution.metadata.get("auto_approved") is True
    assert execution.approved_by == "safety_policy"


def test_action_executor_external_action_cannot_be_silently_auto_approved(temp_workspace):
    """External actions (e.g. calendar/github) must pause in waiting_approval even if auto_approve=True."""
    executor = temp_workspace.actions

    execution = executor.execute(
        action_id="calendar.create_event",
        workspace_id="p12_ws",
        input_data={"title": "Team Sync", "start_time": "2026-10-01T10:00:00Z"},
        auto_approve=True,  # Safety policy should refuse blind auto-approval for EXTERNAL actions
    )
    assert execution.status == ActionExecutionStatus.WAITING_APPROVAL
    assert execution.is_waiting_approval() is True
    assert execution.metadata.get("requires_approval") is True


def test_action_executor_approve_reject_idempotency(temp_workspace):
    """Verify approve and reject idempotency and cross-decision rejection."""
    executor = temp_workspace.actions

    execution = executor.execute(
        action_id="calendar.create_event",
        workspace_id="p12_ws",
        input_data={"title": "Client Meeting", "start_time": "2026-10-01T12:00:00Z"},
        auto_approve=False,
    )
    assert execution.status == ActionExecutionStatus.WAITING_APPROVAL

    # Approve once
    res1 = executor.approve(execution.id, approver="alice")
    assert res1.status == ActionExecutionStatus.SUCCEEDED
    assert res1.approved_by == "alice"

    # Approve again (idempotent)
    res2 = executor.approve(execution.id, approver="alice")
    assert res2.id == execution.id
    assert res2.status == ActionExecutionStatus.SUCCEEDED

    # Cannot reject already approved/succeeded execution
    with pytest.raises(ValueError, match="already approved"):
        executor.reject(execution.id, reason="Changed mind")


def test_action_executor_reject_flow(temp_workspace):
    """Verify reject transitions to REJECTED and forbids subsequent approval."""
    executor = temp_workspace.actions

    execution = executor.execute(
        action_id="calendar.create_event",
        workspace_id="p12_ws",
        input_data={"title": "Spam Meeting", "start_time": "2026-10-01T12:00:00Z"},
        auto_approve=False,
    )
    assert execution.status == ActionExecutionStatus.WAITING_APPROVAL

    # Reject once
    res1 = executor.reject(execution.id, reason="Not authorized")
    assert res1.status == ActionExecutionStatus.REJECTED
    assert res1.rejection_reason == "Not authorized"

    # Reject again (idempotent)
    res2 = executor.reject(execution.id, reason="Not authorized")
    assert res2.status == ActionExecutionStatus.REJECTED

    # Cannot approve already rejected execution
    with pytest.raises(ValueError, match="already declined"):
        executor.approve(execution.id, approver="bob")


def test_action_executor_failure_propagation_no_false_success(temp_workspace):
    """If an action connector or handler fails, executor must transition to FAILED and mask secrets."""
    executor = temp_workspace.actions

    # Mock connector execution returning success=False
    mock_connector_res = MagicMock()
    mock_connector_res.success = False
    mock_connector_res.error = "Connection refused to remote server with token secret_token_xyz"
    mock_connector_res.data = {}

    with patch.object(executor, "_run_provider_connector", side_effect=RuntimeError("Connector error: token secret_token_xyz failed")):
        # Register a dummy action using external provider
        executor.registry.register(
            ActionDefinition(
                id="github.failing_provider",
                name="Failing Provider Action",
                description="Simulates remote provider failure",
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                provider="github",
            )
        )

        execution = executor.execute(
            action_id="github.failing_provider",
            workspace_id="p12_ws",
            input_data={"auth_token": "secret_token_xyz"},
            auto_approve=True,
        )

        assert execution.status == ActionExecutionStatus.FAILED
        assert execution.is_terminal() is True
        assert "secret_token_xyz" not in execution.error_message


# ---------------------------------------------------------------------------
# 3. Deliverable On-Disk Verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deliverable_approval_fails_if_file_missing_on_disk(temp_workspace):
    """Approving a deliverable whose file does not exist on disk must return HTTP 400."""
    store = temp_workspace.missions

    mission = store.create_mission(
        title="Deliverable Check Mission",
        objective="Verify disk safety",
        workspace_id="p12_ws",
    )

    deliv = Deliverable(
        id="del-ghost-01",
        mission_id=mission.id,
        name="Quarterly_Report.pdf",
        path="/nonexistent/path/to/Quarterly_Report.pdf",
        status="draft",
    )
    store.add_deliverable(mission.id, deliv)

    req = make_request()
    payload = CanonicalApprovalPayload(
        target_type="deliverable",
        approver="auditor",
        workspace_id="p12_ws",
    )

    with pytest.raises(HTTPException) as exc_info:
        await _handle_canonical_approval(req, "del-ghost-01", "approve", payload)

    assert exc_info.value.status_code == 400
    assert "does not exist on disk" in exc_info.value.detail


@pytest.mark.asyncio
async def test_deliverable_approval_succeeds_if_file_exists_on_disk(temp_workspace):
    """Approving a deliverable whose file exists on disk updates status to 'verified'."""
    store = temp_workspace.missions

    mission = store.create_mission(
        title="Deliverable Check Mission",
        objective="Verify disk safety",
        workspace_id="p12_ws",
    )

    # Create real file on disk
    report_file = Path(temp_workspace.root) / "Real_Report.pdf"
    report_file.write_text("Authoritative audit report content.")

    deliv = Deliverable(
        id="del-real-01",
        mission_id=mission.id,
        name="Real_Report.pdf",
        path=str(report_file),
        status="draft",
    )
    store.add_deliverable(mission.id, deliv)

    req = make_request()
    payload = CanonicalApprovalPayload(
        target_type="deliverable",
        approver="auditor",
        workspace_id="p12_ws",
    )

    res = await _handle_canonical_approval(req, "del-real-01", "approve", payload)
    assert res["success"] is True
    assert res["status"] == "approved"

    # Verify deliverable in store is now verified
    updated_deliv = store.get_deliverable("del-real-01")
    assert updated_deliv.status == "verified"
    assert updated_deliv.metadata.get("approved_by") == "auditor"


# ---------------------------------------------------------------------------
# 4. Personal Agent Service Step Truthfulness & Notification Suppression
# ---------------------------------------------------------------------------

def test_personal_agent_do_tier_failure_suppresses_completed_notification(temp_workspace):
    """When a DO tier action fails, the response must report error and NOT notify ACTION_COMPLETED."""
    agent_svc = temp_workspace.personal
    notif_svc = temp_workspace.notifications
    initial_completed_count = len([n for n in notif_svc.store.list("p12_ws") if n.type == NotificationType.ACTION_COMPLETED])

    # Mock runtime.execute to simulate DO tier failure
    failing_result = ExecutionResult(
        success=False,
        status=ExecutionStatus.FAILED,
        error="Filesystem error: disk quota exceeded",
        execution_id="task-fail-99",
    )

    with patch.object(agent_svc.runtime, "execute", return_value=failing_result):
        # Trigger DO tier intent
        intent = UserIntent(
            raw_prompt="create a file named report.txt",
            tier=IntentTier.DO,
            summary="Create report file",
            action_id="files.create_document",
            action_args={"filename": "report.txt", "content": "test"},
        )

        with patch.object(agent_svc, "classify_intent", return_value=intent):
            msg = agent_svc.process_prompt("p12_ws", "create a file named report.txt")

            # Must NOT report success in conversational text
            assert "taken care of it" not in msg.content.lower()
            assert "failed" in msg.content.lower() or "disk quota" in msg.content.lower()

            # The step must be marked as failed
            step_exec = next((s for s in msg.steps if s.category == "action"), None)
            assert step_exec is not None
            assert step_exec.status == "failed"

            # No ACTION_COMPLETED notification should have been dispatched
            after_completed_count = len([n for n in notif_svc.store.list("p12_ws") if n.type == NotificationType.ACTION_COMPLETED])
            assert after_completed_count == initial_completed_count


def test_personal_agent_act_tier_waiting_approval_truthful(temp_workspace):
    """When an ACT tier action pauses for approval, step must be waiting_approval, not completed."""
    agent_svc = temp_workspace.personal

    waiting_result = ExecutionResult(
        success=True,
        status=ExecutionStatus.WAITING_FOR_APPROVAL,
        output="ACTION REQUIRES APPROVAL",
        execution_id="task-act-01",
        metadata={"action_execution_id": "ax-act-01"},
    )

    with patch.object(agent_svc.runtime, "execute", return_value=waiting_result):
        intent = UserIntent(
            raw_prompt="schedule a calendar meeting with client",
            tier=IntentTier.ACT,
            summary="Schedule calendar event",
            action_id="calendar.create_event",
            action_args={"title": "Client Sync", "start_time": "2026-10-01T10:00:00Z"},
        )

        with patch.object(agent_svc, "classify_intent", return_value=intent):
            msg = agent_svc.process_prompt("p12_ws", "schedule a calendar meeting with client")

            # Check that an approval step exists with waiting_approval (or pending_approval) status
            appr_step = next((s for s in msg.steps if "approval" in s.title.lower()), None)
            assert appr_step is not None
            assert appr_step.status in ("waiting_approval", "pending_approval")
            assert appr_step.status != "completed"
