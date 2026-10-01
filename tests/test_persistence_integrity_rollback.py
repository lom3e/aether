import sqlite3
import pytest
from datetime import datetime, timezone
from aether.workspace.workspace import Workspace
from aether.personal.store import PersonalStore
from aether.planning.contracts import (
    IntentRequest,
    MissionProposal,
    ProposalStatus,
    ContextPack,
)


def test_unique_constraint_intent_and_version(tmp_path):
    db_path = tmp_path / "personal.db"
    store = PersonalStore(db_path)
    ws_id = "test_workspace"

    intent = IntentRequest(
        id="intent-unique-001",
        workspace_id=ws_id,
        raw_input="Perform unique test",
    )
    store.save_intent_request(intent)

    prop1 = MissionProposal(
        id="prop-unique-001",
        intent_id=intent.id,
        workspace_id=ws_id,
        title="Proposal V1",
        objective="Run first version",
        why="Testing unique constraint",
        context_summary="Context summary V1",
        confidence=0.9,
        version=1,
    )
    store.save_proposal(prop1)

    # Attempting to save another proposal with the same intent_id and version=1 must fail unique constraint
    prop2 = MissionProposal(
        id="prop-unique-002",
        intent_id=intent.id,
        workspace_id=ws_id,
        title="Duplicate Proposal V1",
        objective="Conflict version",
        why="Testing duplicate constraint",
        context_summary="Context summary V2",
        confidence=0.9,
        version=1,
    )
    with pytest.raises(ValueError, match="Proposal integrity violation"):
        store.save_proposal(prop2)


def test_transaction_rollback_on_failure(tmp_path):
    db_path = tmp_path / "personal_rollback.db"
    store = PersonalStore(db_path)
    ws_id = "test_workspace"

    intent_id = "intent-rollback-001"

    # Simulate an atomic transaction where an error occurs during multi-step operation
    with pytest.raises(RuntimeError):
        with store.transaction() as conn:
            # 1. Insert intent
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO intent_requests (id, workspace_id, raw_input, source_surface, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (intent_id, ws_id, "Failing transaction", "api", "received", now),
            )
            # 2. Simulate unexpected failure before commit
            raise RuntimeError("Simulated transaction abort")

    # Verify intent was rolled back and does not exist in store
    assert store.get_intent_request(intent_id) is None


def test_atomic_transition_proposal_status(tmp_path):
    db_path = tmp_path / "personal_state.db"
    store = PersonalStore(db_path)
    ws_id = "test_workspace"

    intent = IntentRequest(
        id="intent-state-001",
        workspace_id=ws_id,
        raw_input="Perform state transitions",
    )
    store.save_intent_request(intent)

    prop = MissionProposal(
        id="prop-state-001",
        intent_id=intent.id,
        workspace_id=ws_id,
        title="Proposal Lifecycle",
        objective="Verify state transitions",
        why="Testing proposal state transitions",
        context_summary="Context summary for state",
        confidence=0.95,
        status=ProposalStatus.READY_FOR_ACCEPTANCE,
        version=1,
    )
    store.save_proposal(prop)

    # 1. Transition with wrong expected from_status fails closed with ValueError
    with pytest.raises(ValueError, match="cannot transition from"):
        store.transition_proposal_status(
            proposal_id=prop.id,
            workspace_id=ws_id,
            from_status=ProposalStatus.ACCEPTED,
            to_status=ProposalStatus.REVOKED,
        )
    current = store.get_proposal(prop.id, workspace_id=ws_id)
    assert current is not None
    assert current.status == ProposalStatus.READY_FOR_ACCEPTANCE

    # 2. Transition with matching from_status succeeds
    updated = store.transition_proposal_status(
        proposal_id=prop.id,
        workspace_id=ws_id,
        from_status=ProposalStatus.READY_FOR_ACCEPTANCE,
        to_status=ProposalStatus.ACCEPTED,
    )
    assert updated.status == ProposalStatus.ACCEPTED
    current = store.get_proposal(prop.id, workspace_id=ws_id)
    assert current.status == ProposalStatus.ACCEPTED

    # 3. Transition from ACCEPTED to REVOKED succeeds
    revoked = store.transition_proposal_status(
        proposal_id=prop.id,
        workspace_id=ws_id,
        from_status=ProposalStatus.ACCEPTED,
        to_status=ProposalStatus.REVOKED,
    )
    assert revoked.status == ProposalStatus.REVOKED
    current = store.get_proposal(prop.id, workspace_id=ws_id)
    assert current.status == ProposalStatus.REVOKED
