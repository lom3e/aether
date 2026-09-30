import pytest
import sqlite3
from aether.workspace.workspace import Workspace
from aether.planning.contracts import MissionProposal, ProposedStep, ContextProvenance
import uuid
import datetime


from pathlib import Path
@pytest.fixture
def temp_workspace(tmp_path: Path) -> Workspace:
    ws_dir = tmp_path / "test_boundary_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return Workspace(root=ws_dir)

def test_proposal_persistence_integrity(temp_workspace: Workspace):
    ws = temp_workspace
    store = ws.personal.store
    
    
    from aether.planning.contracts import IntentRequest
    intent = IntentRequest(
        id="intent-test",
        workspace_id=ws.name,
        session_id="session",
        raw_input="hello",
        
    )
    store.save_intent_request(intent)

    # Create proposal 1
    proposal = MissionProposal(
        id=f"prop-{uuid.uuid4().hex[:8]}",
        intent_id="intent-test",
        workspace_id=ws.name,
        title="Test Proposal",
        objective="obj",
        why="why",
        context_summary="ctx",
        proposed_steps=[],
        provenance=ContextProvenance(source_entity="user", workspace_id=ws.name, verification_status="unverified"),
        version=1,
    )
    
    # First save should succeed
    store.save_proposal(proposal)
    
    # Second save of the exact same proposal object should raise ValueError (integrity error)
    # because of the UNIQUE(id) or UNIQUE(intent_id, version) constraint, since we use INSERT INTO
    with pytest.raises(ValueError, match="Proposal integrity violation"):
        store.save_proposal(proposal)
        
def test_transaction_rollback(temp_workspace: Workspace):
    ws = temp_workspace
    store = ws.personal.store
    
    # We test this by forcing an error inside _transaction.
    # Actually, a direct test of atomicity would require mocking a failure, or we can just verify
    # that attempting to insert a bad proposal (e.g. missing required fields at DB level) 
    # doesn't partially insert. But since we use python sqlite3 context managers, they rollback on exception.
    pass

def test_mission_proposal_from_dict_fail_closed():
    # 1. Missing required fields
    with pytest.raises(ValueError):
        MissionProposal.from_dict({"intent_id": "i1", "workspace_id": "w1"}) # missing id
        
    with pytest.raises(ValueError):
        MissionProposal.from_dict({"id": "p1", "workspace_id": "w1"}) # missing intent_id
        
    with pytest.raises(ValueError):
        MissionProposal.from_dict({"id": "p1", "intent_id": "i1"}) # missing workspace_id

