"""
Exhaustive test suite for Macro-pass P0.4 — Approvals and Require Review.
Verifies:
  1. Canonical approval notification fields (open_target, approve_action, reject_action).
  2. ActionExecutor idempotency on approve and reject (already approved, already rejected, cross-transitions).
  3. MissionRuntime gate approval/rejection idempotency.
  4. Unified canonical approval endpoints:
     - GET  /api/approvals/{target_id}
     - POST /api/approvals/{target_id}/approve
     - POST /api/approvals/{target_id}/reject
     - Auto-dismissal/read receipt of matching notifications upon decision.
  5. PersonalAgentService truthful step status (no fake completion in ACT/DO tiers).
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
from starlette.requests import Request
from fastapi import HTTPException

from aether.actions.models import (
    ActionExecutionStatus,
)
from aether.missions.models import (
    ExecutionStatus,
)
from aether.missions.runtime import MissionRuntime
from aether.notifications.models import (
    Notification,
    NotificationPriority,
    NotificationStatus,
    NotificationTargetType,
    NotificationType,
)
from aether.notifications.store import NotificationStore
from aether.personal.models import (
    IntentTier,
)
from aether.server.app import app
from aether.server.routes import (
    CanonicalApprovalPayload,
    approve_canonical_target_route,
    get_approval_status_route,
    reject_canonical_target_route,
)
from aether.workspace.workspace import Workspace


def make_request(method: str = "GET", path: str = "/") -> Request:
    scope = {"type": "http", "app": app, "headers": [], "path": path, "method": method}
    return Request(scope)


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Workspace.init(Path(tmp_dir), name="p04_ws")
        app.state.workspace = ws
        yield ws
        ws.close()


# ---------------------------------------------------------------------------
# 1. Canonical Notification Approval Payload & Actions
# ---------------------------------------------------------------------------

def test_canonical_approval_notification_structure():
    """Verify that approval notifications auto-generate canonical open_target, approve_action, and reject_action."""
    notif = Notification(
        id="notif-review-01",
        workspace_id="p04_ws",
        type=NotificationType.APPROVAL_REQUIRED,
        title="High-Risk Action Approval",
        message="Execution of deploy_database requires review",
        priority=NotificationPriority.HIGH,
        target_type=NotificationTargetType.ACTION_EXECUTION,
        target_id="exec-deploy-99",
    )

    data = notif.to_dict()
    assert data["open_target"] is not None
    assert data["open_target"]["view"] == "connections"
    assert data["open_target"]["params"] == "exec-deploy-99"
    assert data["open_target"]["target_type"] == "action_execution"
    assert "exec-deploy-99" in data["open_target"]["deep_link"]

    assert data["approve_action"] is not None
    assert data["approve_action"]["method"] == "POST"
    assert data["approve_action"]["endpoint"] == "/api/approvals/exec-deploy-99/approve"
    assert data["approve_action"]["target_id"] == "exec-deploy-99"

    assert data["reject_action"] is not None
    assert data["reject_action"]["method"] == "POST"
    assert data["reject_action"]["endpoint"] == "/api/approvals/exec-deploy-99/reject"
    assert data["reject_action"]["target_id"] == "exec-deploy-99"

    # Deserialization test
    restored = Notification.from_dict(data)
    assert restored.open_target["view"] == "connections"
    assert restored.approve_action["endpoint"] == "/api/approvals/exec-deploy-99/approve"
    assert restored.reject_action["endpoint"] == "/api/approvals/exec-deploy-99/reject"


def test_canonical_mission_approval_notification():
    """Verify mission gate review generates open_target to missions view."""
    notif = Notification(
        id="notif-msn-01",
        workspace_id="p04_ws",
        type=NotificationType.APPROVAL_REQUIRED,
        title="Mission Gate Review",
        message="Mission Marketing Launch is paused for review",
        target_type=NotificationTargetType.MISSION,
        target_id="msn-marketing-1",
    )

    data = notif.to_dict()
    assert data["open_target"]["view"] == "missions"
    assert data["open_target"]["params"] == "msn-marketing-1"
    assert data["approve_action"]["endpoint"] == "/api/approvals/msn-marketing-1/approve"
    assert data["reject_action"]["endpoint"] == "/api/approvals/msn-marketing-1/reject"


# ---------------------------------------------------------------------------
# 2. ActionExecutor Idempotency (Approve / Reject)
# ---------------------------------------------------------------------------

def test_action_executor_approve_idempotent(temp_workspace):
    executor = temp_workspace.actions

    # Initial execution request requires approval (ACT tier)
    execution = executor.execute(
        action_id="calendar.create_event",
        workspace_id="p04_ws",
        input_data={"title": "Important Meeting", "start_time": "2026-10-01T10:00:00Z"},
        auto_approve=False,
    )
    assert execution.status == ActionExecutionStatus.PENDING_APPROVAL

    # Approve once: executes action and returns
    approved_exec = executor.approve(execution.id, approver="admin")
    assert approved_exec.status in (ActionExecutionStatus.APPROVED, ActionExecutionStatus.SUCCESS)

    # Approve AGAIN (idempotent call): must return safely without error
    second_approved_exec = executor.approve(execution.id, approver="admin")
    assert second_approved_exec.id == execution.id
    assert second_approved_exec.status in (ActionExecutionStatus.APPROVED, ActionExecutionStatus.SUCCESS)

    # Rejecting an already approved execution must fail with clean explanation
    with pytest.raises(ValueError, match="already approved"):
        executor.reject(execution.id, reason="Changed mind")


def test_action_executor_reject_idempotent(temp_workspace):
    executor = temp_workspace.actions

    execution = executor.execute(
        action_id="calendar.create_event",
        workspace_id="p04_ws",
        input_data={"title": "Risky Event", "start_time": "2026-10-02T10:00:00Z"},
        auto_approve=False,
    )
    assert execution.status == ActionExecutionStatus.PENDING_APPROVAL

    # Reject once
    rejected_exec = executor.reject(execution.id, reason="Not authorized")
    assert rejected_exec.status == ActionExecutionStatus.REJECTED

    # Reject AGAIN (idempotent call): must return cleanly
    second_rejected_exec = executor.reject(execution.id, reason="Already declined")
    assert second_rejected_exec.id == execution.id
    assert second_rejected_exec.status == ActionExecutionStatus.REJECTED

    # Approving an already rejected execution must fail with clean explanation
    with pytest.raises(ValueError, match="already declined"):
        executor.approve(execution.id, approver="admin")


# ---------------------------------------------------------------------------
# 3. MissionRuntime Gate Idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mission_runtime_approve_and_reject_gate_idempotent(temp_workspace):
    store = temp_workspace.missions
    runtime = MissionRuntime(workspace=temp_workspace)

    mission = store.create_mission(
        title="Gate Test Mission",
        objective="Tests approval gates",
        milestones=[
            {"title": "Step 1", "order_idx": 0},
            {"title": "[Approval Gate] Step 2", "description": "[Approval] Manual check", "order_idx": 1},
        ],
    )

    # Fake execution in AWAITING_APPROVAL state
    execution = store.create_execution(
        mission_id=mission.id,
        team_name="test_team",
        run_number=1,
    )
    store.update_execution(
        execution.id,
        status=ExecutionStatus.AWAITING_APPROVAL,
        pending_approval={"id": "gate-1", "type": "stage_gate", "prompt": "Review Step 2"},
    )

    # 1. Approve gate
    approved = await runtime.approve_gate(mission.id, approval_id="gate-1", notes="Approved")
    assert approved.status == ExecutionStatus.RUNNING

    # 2. Approve gate AGAIN (idempotent: execution is RUNNING)
    second_call = await runtime.approve_gate(mission.id, approval_id="gate-1", notes="Approved again")
    assert second_call.status in (ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED)

    # 3. Rejection test on a separate mission
    mission2 = store.create_mission(
        title="Gate Test Mission 2",
        objective="Tests reject gates",
        milestones=[
            {"title": "Step 1", "order_idx": 0},
            {"title": "[Approval Gate] Step 2", "order_idx": 1},
        ],
    )
    exec2 = store.create_execution(
        mission_id=mission2.id,
        team_name="test_team",
        run_number=1,
    )
    store.update_execution(
        exec2.id,
        status=ExecutionStatus.AWAITING_APPROVAL,
        pending_approval={"id": "gate-2", "type": "stage_gate", "prompt": "Review Step 2"},
    )

    # Reject once
    rejected = await runtime.reject_gate(mission2.id, approval_id="gate-2", feedback="Rejected by test")
    assert rejected.status == ExecutionStatus.INTERRUPTED

    # Reject AGAIN: idempotent
    second_reject = await runtime.reject_gate(mission2.id, approval_id="gate-2", feedback="Rejected again")
    assert second_reject.status == ExecutionStatus.INTERRUPTED


# ---------------------------------------------------------------------------
# 4. Canonical Approval REST Routes & Notification Dismissal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_canonical_approval_endpoints_action_flow(temp_workspace):
    """Test GET details, POST approve, and POST reject on /api/approvals/{id}."""
    executor = temp_workspace.actions
    notif_store = NotificationStore(db_path=temp_workspace.notifications_db_path)

    # Create pending execution
    execution = executor.execute(
        action_id="calendar.create_event",
        workspace_id=temp_workspace.name,
        input_data={"title": "Client Sync", "start_time": "2026-10-10T12:00:00Z"},
        auto_approve=False,
    )

    # Create associated unread notification
    notif = Notification(
        id="notif-restart-1",
        workspace_id=temp_workspace.name,
        type=NotificationType.APPROVAL_REQUIRED,
        title="Client Sync Review",
        message="Review calendar create event",
        target_type=NotificationTargetType.ACTION_EXECUTION,
        target_id=execution.id,
    )
    notif_store.save(notif)
    assert notif_store.get("notif-restart-1").status == NotificationStatus.UNREAD

    req = make_request("GET", f"/api/approvals/{execution.id}")

    # 1. GET /api/approvals/{id}
    details = await get_approval_status_route(
        req,
        target_id=execution.id,
    )
    assert details["target_id"] == execution.id
    assert details["status"] in ("pending_approval", "waiting_approval")
    assert details["target_type"] == "action_execution"
    assert details["approve_action"]["endpoint"] == f"/api/approvals/{execution.id}/approve"

    # 2. POST /api/approvals/{id}/approve
    payload = CanonicalApprovalPayload(
        target_type="action_execution",
        approver="admin",
        workspace_id=temp_workspace.name,
    )
    res1 = await approve_canonical_target_route(req, target_id=execution.id, payload=payload)
    assert res1["success"] is True
    assert res1["target_id"] == execution.id
    assert res1["status"] in ("approved", "success")

    # Verify notification was auto-marked as read
    updated_notif = notif_store.get("notif-restart-1")
    assert updated_notif.status == NotificationStatus.READ

    # 3. POST /api/approvals/{id}/approve AGAIN (idempotency)
    res2 = await approve_canonical_target_route(req, target_id=execution.id, payload=payload)
    assert res2["success"] is True
    assert res2["status"] == "already_completed"
    assert "already" in res2["message"].lower()


@pytest.mark.asyncio
async def test_canonical_approval_reject_flow(temp_workspace):
    executor = temp_workspace.actions
    notif_store = NotificationStore(db_path=temp_workspace.notifications_db_path)

    execution = executor.execute(
        action_id="calendar.create_event",
        workspace_id=temp_workspace.name,
        input_data={"title": "Declined Sync", "start_time": "2026-10-10T12:00:00Z"},
        auto_approve=False,
    )

    notif = Notification(
        id="notif-wipe-1",
        workspace_id=temp_workspace.name,
        type=NotificationType.APPROVAL_REQUIRED,
        title="Sync Review",
        message="Review sync",
        target_type=NotificationTargetType.ACTION_EXECUTION,
        target_id=execution.id,
    )
    notif_store.save(notif)

    req = make_request("POST", f"/api/approvals/{execution.id}/reject")

    payload = CanonicalApprovalPayload(
        target_type="action_execution",
        approver="admin",
        reason="Blocked by policy",
        workspace_id=temp_workspace.name,
    )
    res1 = await reject_canonical_target_route(req, target_id=execution.id, payload=payload)
    assert res1["success"] is True
    assert res1["status"] == "rejected"

    # Notification marked read
    assert notif_store.get("notif-wipe-1").status == NotificationStatus.READ

    # Repeated reject call is idempotent
    res2 = await reject_canonical_target_route(req, target_id=execution.id, payload=payload)
    assert res2["success"] is True
    assert res2["status"] == "already_completed"


@pytest.mark.asyncio
async def test_canonical_approval_unknown_target_404(temp_workspace):
    req = make_request("GET", "/api/approvals/non-existent-target")

    with pytest.raises(HTTPException) as exc_info:
        await get_approval_status_route(
            req, target_id="non-existent-target"
        )
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# 5. PersonalAgentService Truthful Step Statuses (Forensic Audit #14 & #15)
# ---------------------------------------------------------------------------

def test_personal_agent_truthful_act_and_do_flows(temp_workspace):
    personal_svc = temp_workspace.personal

    # 1. ACT Flow with approval requirement
    res_act = personal_svc.process_prompt(
        workspace_id=temp_workspace.name,
        prompt="Schedule a meeting with investor tomorrow at 9am",
    )
    assert res_act.tier == IntentTier.ACT
    assert res_act.action_execution_id is not None

    # Verify execution is truly pending_approval, not fake completed
    exec_record = temp_workspace.action_store.get_execution(res_act.action_execution_id)
    assert exec_record.status == ActionExecutionStatus.PENDING_APPROVAL

    # 2. DO Flow executes truthfully
    res_do = personal_svc.process_prompt(
        workspace_id=temp_workspace.name,
        prompt="Create a file named notes.md with project overview",
    )
    assert res_do.tier == IntentTier.DO
    assert res_do.action_execution_id is not None
    exec_do = temp_workspace.action_store.get_execution(res_do.action_execution_id)
    assert exec_do.status == ActionExecutionStatus.SUCCESS
