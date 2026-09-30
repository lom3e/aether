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
    
    # Construct a valid authority (normally done by ProposalService)
    auth = ExecutionAuthority(
        proposal_id="prop-123",
        proposal_version=1,
        workspace_id=ws_id,
        granted_at="2026-01-01T00:00:00Z"
    )
    
    # 3. Execution succeeds with authority
    res = ws.actions.execute(
        action_id="calendar.create_event",
        workspace_id=ws_id,
        input_data={"path": "test.txt", "content": "hello"},
        authority=auth,
    )
    # the actual output might be blocked by HITL, but it didn't throw UnauthorizedExecutionError
    assert res.status in (ActionExecutionStatus.COMPLETED, ActionExecutionStatus.PENDING_APPROVAL)

def test_action_executor_boundary_tampering(temp_workspace: Workspace):
    ws = temp_workspace
    ws_id = ws.name
    
    # Tampering: wrong workspace
    auth = ExecutionAuthority(
        proposal_id="prop-123",
        proposal_version=1,
        workspace_id="wrong_workspace",
        granted_at="2026-01-01T00:00:00Z"
    )
    
    with pytest.raises(UnauthorizedExecutionError):
        ws.actions.execute(
            action_id="calendar.create_event",
            workspace_id=ws_id,
            input_data={"path": "test.txt", "content": "hello"},
            authority=auth,
        )

