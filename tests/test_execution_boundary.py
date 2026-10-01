import pytest
from aether.core.execution import ExecutionAuthority, UnauthorizedExecutionError
from aether.actions.models import ActionExecutionStatus
from aether.workspace.workspace import Workspace


from pathlib import Path
@pytest.fixture
def temp_workspace(tmp_path: Path) -> Workspace:
    ws_dir = tmp_path / "test_boundary_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return Workspace(root=ws_dir)

def test_action_executor_boundary_negative(temp_workspace: Workspace):
    ws = temp_workspace
    ws_id = ws.name
    
    # 1. Action requiring authority
    with pytest.raises(UnauthorizedExecutionError):
        ws.actions.execute(
            action_id="calendar.create_event",
            workspace_id=ws_id,
            input_data={"path": "test.txt", "content": "hello"},
        )
        
    # 2. auto_approve does not bypass authority
    with pytest.raises(UnauthorizedExecutionError):
        ws.actions.execute(
            action_id="calendar.create_event",
            workspace_id=ws_id,
            input_data={"path": "test.txt", "content": "hello"},
            auto_approve=True,
        )

def test_action_executor_boundary_positive(temp_workspace: Workspace):
    ws = temp_workspace
    ws_id = ws.name
    
    # 1. Create a valid intent and proposal in personal store
    from datetime import datetime, timezone
    from aether.planning.contracts import IntentRequest, MissionProposal, ProposalStatus
    ws.personal_store.save_intent_request(IntentRequest(
        id="intent-exec-1",
        workspace_id=ws_id,
        raw_input="Create calendar event",
        source_surface="test",
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    proposal = MissionProposal(
        id="prop-valid-exec-1",
        intent_id="intent-exec-1",
        workspace_id=ws_id,
        title="Valid Execution Proposal",
        objective="Create calendar event",
        why="User requested event",
        context_summary="Calendar context",
        confidence=1.0,
        status=ProposalStatus.READY_FOR_ACCEPTANCE,
    )
    ws.personal_store.save_proposal(proposal)

    # 2. Accept the proposal via PersonalService to issue authoritative ExecutionAuthority
    accepted_prop, auth = ws.personal.accept_proposal(
        proposal_id=proposal.id,
        workspace_id=ws_id,
        expected_version=1,
    )
    
    # 3. Execution succeeds with authority
    res = ws.actions.execute(
        action_id="calendar.create_event",
        workspace_id=ws_id,
        input_data={"path": "test.txt", "content": "hello"},
        authority=auth,
    )
    # the actual output might be blocked by HITL, but it didn't throw UnauthorizedExecutionError
    assert res.status in (ActionExecutionStatus.SUCCEEDED, ActionExecutionStatus.WAITING_APPROVAL)

def test_action_executor_boundary_tampering(temp_workspace: Workspace):
    ws = temp_workspace
    ws_id = ws.name
    
    # 1. Tampering: non-existent proposal
    auth_nonexistent = ExecutionAuthority(
        proposal_id="prop-nonexistent",
        proposal_version=1,
        workspace_id=ws_id,
        granted_at="2026-01-01T00:00:00Z"
    )
    with pytest.raises(UnauthorizedExecutionError):
        ws.actions.execute(
            action_id="calendar.create_event",
            workspace_id=ws_id,
            input_data={"path": "test.txt", "content": "hello"},
            authority=auth_nonexistent,
        )

    # 2. Create a valid accepted proposal
    from datetime import datetime, timezone
    from aether.planning.contracts import IntentRequest, MissionProposal, ProposalStatus
    ws.personal_store.save_intent_request(IntentRequest(
        id="intent-tamper-1",
        workspace_id=ws_id,
        raw_input="Create calendar event",
        source_surface="test",
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    proposal = MissionProposal(
        id="prop-valid-tamper-1",
        intent_id="intent-tamper-1",
        workspace_id=ws_id,
        title="Tamper Test Proposal",
        objective="Create calendar event",
        why="User requested event",
        context_summary="Calendar context",
        confidence=1.0,
        status=ProposalStatus.READY_FOR_ACCEPTANCE,
    )
    ws.personal_store.save_proposal(proposal)
    accepted_prop, valid_auth = ws.personal.accept_proposal(
        proposal_id=proposal.id,
        workspace_id=ws_id,
    )

    # 3. Tampering: wrong workspace
    auth_wrong_ws = ExecutionAuthority(
        proposal_id=proposal.id,
        proposal_version=1,
        workspace_id="wrong_workspace",
        granted_at="2026-01-01T00:00:00Z"
    )
    with pytest.raises(UnauthorizedExecutionError):
        ws.actions.execute(
            action_id="calendar.create_event",
            workspace_id=ws_id,
            input_data={"path": "test.txt", "content": "hello"},
            authority=auth_wrong_ws,
        )

    # 4. Tampering: wrong version
    auth_wrong_ver = ExecutionAuthority(
        proposal_id=proposal.id,
        proposal_version=999,
        workspace_id=ws_id,
        granted_at="2026-01-01T00:00:00Z"
    )
    with pytest.raises(UnauthorizedExecutionError):
        ws.actions.execute(
            action_id="calendar.create_event",
            workspace_id=ws_id,
            input_data={"path": "test.txt", "content": "hello"},
            authority=auth_wrong_ver,
        )

