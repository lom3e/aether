"""
End-to-End HTTP Gate and User Lifecycle Tests for Coding Delegation.
Verifies the complete three-phase architecture:
- Phase 1: Accettazione della Proposta (MissionProposal -> Authority token)
- Phase 2: Approvazione dell'Esecuzione (coding.delegate HITL gate -> Execution waiting_approval)
- Phase 3: Verificabilità dello Stato e dei Risultati (Status, Diff, Modified files, Automated Test Outcomes)
Also verifies negative safety controls, fail-closed boundaries, and status inquiry routing.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi import Request

from aether.actions.models import ActionExecutionStatus
from aether.coding.models import (
    CodingExecutionStatus,
    CodingResult,
    CodingTask,
    CodingTaskExecution,
)
from aether.coding.orchestrator import CodingAgentOrchestrator
from aether.core.execution import UnauthorizedExecutionError
from aether.server.app import app
from aether.server.routes import (
    personal_chat_route,
    accept_proposal_route,
    approve_canonical_target_route,
    reject_canonical_target_route,
    get_personal_overview_route,
    get_action_execution_route,
    list_coding_providers_route,
    set_coding_preferences_route,
    PersonalChatPayload,
    AcceptProposalPayload,
    CanonicalApprovalPayload,
    CodingPreferencesPayload,
)
from aether.workspace.workspace import Workspace


@pytest.fixture
def temp_workspace(tmp_path: Path):
    ws_dir = tmp_path / "aether_test_workspace"
    ws = Workspace.init(ws_dir, name="Aether Test Workspace")
    app.state.workspace = ws
    yield ws
    ws.close()


def make_request(method: str = "GET", path: str = "/") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "app": app,
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_coding_delegation_three_phase_http_lifecycle(temp_workspace, tmp_path: Path):
    """
    Validates the full 3-phase flow over the HTTP surface:
    1. Chat prompt -> Phase 1 proposal created (ACT tier).
    2. Phase 1 Accept proposal -> ExecutionAuthority granted.
    3. Chat prompt with authority -> Phase 2 HITL gate (waiting_approval).
    4. Overview endpoint shows pending approval.
    5. Phase 2 Approve -> coding.delegate execution completes with diff and test evidence.
    6. Chat status inquiry -> coding.status returns completed status with diff.
    """
    ws = temp_workspace
    repo_dir = tmp_path / "mock_project_repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()

    prompt = f"Implement calculate_median function to make tests pass in {repo_dir}"

    # --- STEP 1: Chat Request without Authority -> Proposal Generation ---
    req1 = make_request("POST", "/api/personal/chat")
    res1 = await personal_chat_route(req1, PersonalChatPayload(prompt=prompt, workspace_id=ws.name))

    assert res1["role"] == "assistant"
    assert res1["tier"] == "act"
    prop = res1.get("proposal") or res1.get("metadata", {}).get("proposal")
    assert prop is not None
    proposal_id = prop["id"]
    assert prop["status"] in ("draft", "ready_for_acceptance")

    # --- STEP 2: Phase 1 - Accept Proposal ---
    req2 = make_request("POST", f"/api/personal/proposals/{proposal_id}/accept")
    res2 = await accept_proposal_route(req2, proposal_id=proposal_id, payload=AcceptProposalPayload(actor="test_user"))

    assert res2["status"] == "accepted"
    authority = res2["authority"]
    assert authority["proposal_id"] == proposal_id

    # --- STEP 3: Phase 2 - Dispatch with Authority -> HITL Gate ---
    req3 = make_request("POST", "/api/personal/chat")
    res3 = await personal_chat_route(req3, PersonalChatPayload(prompt=prompt, workspace_id=ws.name, authority=authority))

    exec_id = res3.get("action_execution_id")
    assert exec_id is not None

    req_ex = make_request("GET", f"/api/actions/executions/{exec_id}")
    ex_stat = await get_action_execution_route(req_ex, execution_id=exec_id)
    assert ex_stat["status"] == "waiting_approval"

    # --- STEP 4: Overview Visibility ---
    req_ov = make_request("GET", "/api/personal/overview")
    ov = await get_personal_overview_route(req_ov, workspace_id=ws.name)
    pending_ids = [p.get("target_id") or p.get("execution_id") or p.get("id") for p in ov.get("pending_approvals", [])]
    assert exec_id in pending_ids

    # --- STEP 5: Phase 2 Approval -> Provider Delegation & Results Collection ---
    mock_coding_result = CodingResult(
        success=True,
        status=CodingExecutionStatus.COMPLETED,
        provider_id="antigravity",
        external_task_id="conv-mock-123",
        summary="Implemented median calculation in median_calc.py",
        diff="--- a/median_calc.py\n+++ b/median_calc.py\n@@ -1 +1,3 @@\n-raise NotImplementedError\n+return sorted(values)[len(values)//2]",
        modified_files=["median_calc.py"],
        test_output="Tests passed (exit code 0):\n3 passed in 0.01s",
        test_passed=True,
    )
    mock_task_exec = CodingTaskExecution(
        id="ctask-exec-123",
        task=CodingTask(instruction=prompt, project_path=str(repo_dir)),
        provider_id="antigravity",
        status=CodingExecutionStatus.COMPLETED,
        result=mock_coding_result,
        external_task_id="conv-mock-123",
    )

    with patch("aether.coding.orchestrator.CodingAgentOrchestrator.delegate_task", return_value=mock_task_exec):
        req_appr = make_request("POST", f"/api/approvals/{exec_id}/approve")
        appr_res = await approve_canonical_target_route(
            req_appr,
            target_id=exec_id,
            payload=CanonicalApprovalPayload(actor="test_user"),
        )
        assert appr_res.get("status") in ("approved", "succeeded")

    req_ex2 = make_request("GET", f"/api/actions/executions/{exec_id}")
    ex_after = await get_action_execution_route(req_ex2, execution_id=exec_id)
    assert ex_after["status"] == "succeeded"

    output = ex_after["output_data"]
    assert output["success"] is True
    assert output["provider_id"] == "antigravity"
    assert output["modified_files"] == ["median_calc.py"]
    assert output["test_passed"] is True
    assert "3 passed" in output["test_output"]
    assert "median_calc.py" in output["diff"]

    # --- STEP 6: Phase 3 Status Inquiry via Conversational Endpoint ---
    with patch("aether.coding.orchestrator.CodingAgentOrchestrator.collect_results", return_value=mock_coding_result):
        req_status = make_request("POST", "/api/personal/chat")
        res_status = await personal_chat_route(
            req_status,
            PersonalChatPayload(prompt="Qual è lo stato del task di coding?", workspace_id=ws.name),
        )
        assert res_status["role"] == "assistant"
        assert res_status["tier"] == "answer"
        assert "COMPLETED" in res_status["content"]
        assert "median_calc.py" in res_status["content"]


@pytest.mark.asyncio
async def test_coding_delegation_rejection_safety_gate(temp_workspace, tmp_path: Path):
    """
    Validates that rejecting an execution gate cleanly stops mutation
    and transitions the ActionExecution to rejected.
    """
    ws = temp_workspace
    repo_dir = tmp_path / "mock_project_repo"
    repo_dir.mkdir()
    prompt = f"Implement parser in {repo_dir}"

    # Accept proposal
    req1 = make_request("POST", "/api/personal/chat")
    res1 = await personal_chat_route(req1, PersonalChatPayload(prompt=prompt, workspace_id=ws.name))
    prop = res1.get("proposal") or res1.get("metadata", {}).get("proposal")
    prop_id = prop["id"]

    req2 = make_request("POST", f"/api/personal/proposals/{prop_id}/accept")
    res2 = await accept_proposal_route(req2, proposal_id=prop_id, payload=AcceptProposalPayload(actor="user"))
    authority = res2["authority"]

    # Dispatch to create pending execution
    req3 = make_request("POST", "/api/personal/chat")
    res3 = await personal_chat_route(req3, PersonalChatPayload(prompt=prompt, workspace_id=ws.name, authority=authority))
    exec_id = res3["action_execution_id"]

    # Explicitly Reject
    req_rej = make_request("POST", f"/api/approvals/{exec_id}/reject")
    rej_res = await reject_canonical_target_route(
        req_rej,
        target_id=exec_id,
        payload=CanonicalApprovalPayload(actor="user", comment="Plan looks unsafe"),
    )
    assert rej_res.get("status") in ("rejected", "cancelled")

    req_ex = make_request("GET", f"/api/actions/executions/{exec_id}")
    ex_stat = await get_action_execution_route(req_ex, execution_id=exec_id)
    assert ex_stat["status"] in ("rejected", "cancelled")


@pytest.mark.asyncio
async def test_coding_delegation_system_root_protection(temp_workspace):
    """
    Validates that delegating coding tasks to system root directories fails closed.
    """
    ws = temp_workspace
    # A protected system directory that exists on the platform running the test.
    protected = "C:/Windows" if sys.platform == "win32" else "/Library"
    prompt = f"Refactor files in {protected}"

    req1 = make_request("POST", "/api/personal/chat")
    res1 = await personal_chat_route(req1, PersonalChatPayload(prompt=prompt, workspace_id=ws.name))
    prop = res1.get("proposal") or res1.get("metadata", {}).get("proposal")
    prop_id = prop["id"]

    req2 = make_request("POST", f"/api/personal/proposals/{prop_id}/accept")
    res2 = await accept_proposal_route(req2, proposal_id=prop_id)
    authority = res2["authority"]

    req3 = make_request("POST", "/api/personal/chat")
    res3 = await personal_chat_route(req3, PersonalChatPayload(prompt=prompt, workspace_id=ws.name, authority=authority))
    exec_id = res3["action_execution_id"]

    # Attempt to approve delegation to protected directory
    req_appr = make_request("POST", f"/api/approvals/{exec_id}/approve")
    appr_res = await approve_canonical_target_route(req_appr, target_id=exec_id)
    assert appr_res.get("status") in ("failed", "rejected") or appr_res.get("entity", {}).get("status") == "failed"

    req_ex = make_request("GET", f"/api/actions/executions/{exec_id}")
    ex_stat = await get_action_execution_route(req_ex, execution_id=exec_id)
    assert ex_stat["status"] == "failed"
    assert "system root" in str(ex_stat.get("error_message", "")).lower()


@pytest.mark.asyncio
async def test_coding_provider_management_http_endpoints(temp_workspace):
    """
    Validates HTTP endpoints:
    - GET /api/coding/providers
    - POST /api/coding/preferences
    - GET /api/personal/overview with coding_providers and preferred_coding_provider
    """
    ws = temp_workspace

    # 1. GET /api/coding/providers
    req1 = make_request("GET", "/api/coding/providers")
    res1 = await list_coding_providers_route(req1)

    assert "providers" in res1
    assert "preferred_provider_id" in res1
    assert len(res1["providers"]) == 3
    prov_ids = [p["id"] for p in res1["providers"]]
    assert "antigravity" in prov_ids
    assert "claude_code" in prov_ids
    assert "codex" in prov_ids

    # 2. Check overview includes coding_providers and preferred_coding_provider
    req_ov = make_request("GET", "/api/personal/overview")
    ov = await get_personal_overview_route(req_ov, workspace_id=ws.name)
    assert "coding_providers" in ov
    assert len(ov["coding_providers"]) == 3
    assert ov["preferred_coding_provider"] == res1["preferred_provider_id"]

    # 3. POST /api/coding/preferences to set preferred provider
    req2 = make_request("POST", "/api/coding/preferences")
    res2 = await set_coding_preferences_route(
        req2,
        payload=CodingPreferencesPayload(preferred_provider_id="codex"),
    )
    assert res2["success"] is True
    assert res2["preferred_provider_id"] == "codex"

    # Verify durability in database and via subsequent GET
    req3 = make_request("GET", "/api/coding/providers")
    res3 = await list_coding_providers_route(req3)
    assert res3["preferred_provider_id"] == "codex"

    # Also verify overview reflects updated preference
    ov2 = await get_personal_overview_route(req_ov, workspace_id=ws.name)
    assert ov2["preferred_coding_provider"] == "codex"

