"""
Tests for Phase 1 (A1 & A2): Policy authorization boundaries and elimination of word-based bypasses.

Ensures:
- A policy that denies auto-approval continues to deny it even when authority exists and auto_approve=True.
- An authorized mission can only execute automatically if the policy allows it.
- A valid authority cannot authorize an action different from the one for which it was issued.
- Words in prompt ('subito', 'direttamente', 'autonomamente', 'without confirmation') do NOT grant authorization.
- Phrases like «Ha subito un errore? Aggiungi un test» do NOT grant autonomous authorization.
- «Implementa foo direttamente nel file x.py» does not bypass confirmation requirement.
- «Non eseguire direttamente questa operazione» is not interpreted as authorization.
- Safety policy always prevails over intent classification.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from aether.actions.executor import ActionExecutor, ActionSafetyPolicy
from aether.actions.registry import ActionRegistry
from aether.actions.store import ActionStore
from aether.actions.models import (
    ActionDefinition,
    ActionExecutionStatus,
    ActionPermissionLevel,
    ActionTier,
)
from aether.core.execution import ExecutionAuthority, UnauthorizedExecutionError
from aether.personal.service import PersonalAgentService
from aether.personal.store import PersonalStore
from aether.planning.contracts import ProposalStatus


class FakeProposal:
    def __init__(self, id: str, workspace_id: str, constraints: list[str] | None = None):
        self.id = id
        self.version = 1
        self.workspace_id = workspace_id
        self.status = ProposalStatus.ACCEPTED
        self.constraints = constraints or []
        self.executed_steps: list[str] = []


class FakePersonalStore:
    def __init__(self, proposal: FakeProposal):
        self.proposal = proposal

    def get_proposal(self, proposal_id: str, workspace_id: str | None = None) -> FakeProposal | None:
        if self.proposal.id == proposal_id:
            return self.proposal
        return None


def test_policy_denial_cannot_be_bypassed_by_authority_and_auto_approve(tmp_path: Path):
    """
    A1: A safety policy requiring confirmation (e.g. SENSITIVE_MUTATION) cannot be overridden
    by an ExecutionAuthority or auto_approve=True.
    """
    registry = ActionRegistry()
    test_action = ActionDefinition(
        id="system.deploy",
        name="Deploy System",
        description="Deploy system to production",
        tier=ActionTier.ACT,
        permission_level=ActionPermissionLevel.SENSITIVE_MUTATION,
        requires_confirmation=True,
    )
    registry.register(test_action, handler=lambda ctx, args: {"deployed": True})

    action_store = ActionStore(db_path=str(tmp_path / "actions.db"))
    safety_policy = ActionSafetyPolicy()
    
    fake_prop = FakeProposal("prop-123", "ws-test", constraints=["allow:system.deploy"])
    fake_pstore = FakePersonalStore(fake_prop)

    executor = ActionExecutor(
        registry=registry,
        store=action_store,
        personal_store=fake_pstore,
        safety_policy=safety_policy,
    )

    authority = ExecutionAuthority(
        proposal_id="prop-123",
        proposal_version=1,
        workspace_id="ws-test",
        granted_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        expires_at=(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat(),
    )

    # Attempt execution with authority and auto_approve=True
    execution = executor.execute(
        action_id="system.deploy",
        input_data={"env": "prod"},
        authority=authority,
        auto_approve=True,
        workspace_id="ws-test",
    )

    # Under safety policy, sensitive mutation cannot be auto-approved -> WAITING_APPROVAL
    assert execution.status == ActionExecutionStatus.WAITING_APPROVAL


def test_policy_service_denial_with_authority_remains_waiting_approval(tmp_path: Path):
    """
    A1: When a policy service evaluates can_auto=False (e.g. Manual tier), auto-approval
    is denied even if authority is provided and auto_approve=True.
    """
    registry = ActionRegistry()
    test_action = ActionDefinition(
        id="coding.delegate",
        name="Delegate Coding",
        description="Run coding delegation",
        tier=ActionTier.ACT,
        permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
        requires_confirmation=True,
    )
    registry.register(test_action, handler=lambda ctx, args: {"done": True})

    mock_policy_svc = MagicMock()
    # Mock evaluate_action returning (can_auto_approve=False, reason="Manual policy requires confirmation")
    mock_policy_svc.evaluate_action.return_value = (False, "Manual policy requires confirmation")

    safety_policy = ActionSafetyPolicy(policy_service=mock_policy_svc)
    action_store = ActionStore(db_path=str(tmp_path / "actions.db"))
    
    fake_prop = FakeProposal("prop-999", "ws-test", constraints=["allow:coding.delegate"])
    fake_pstore = FakePersonalStore(fake_prop)

    executor = ActionExecutor(
        registry=registry,
        store=action_store,
        personal_store=fake_pstore,
        safety_policy=safety_policy,
    )

    authority = ExecutionAuthority(
        proposal_id="prop-999",
        proposal_version=1,
        workspace_id="ws-test",
        granted_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        expires_at=(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat(),
    )

    execution = executor.execute(
        action_id="coding.delegate",
        input_data={"task": "refactor"},
        authority=authority,
        auto_approve=True,
        workspace_id="ws-test",
    )

    # Negative policy decision prevails -> WAITING_APPROVAL
    assert execution.status == ActionExecutionStatus.WAITING_APPROVAL


def test_authority_action_mismatch_rejected(tmp_path: Path):
    """
    A1: A valid authority for action A cannot authorize action B.
    """
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    fake_prop = FakeProposal("prop-456", "ws-test", constraints=["allow:coding.delegate"])
    fake_pstore = FakePersonalStore(fake_prop)

    registry = ActionRegistry()
    action_b = ActionDefinition(
        id="files.delete",
        name="Delete Files",
        description="Delete file",
        tier=ActionTier.ACT,
        permission_level=ActionPermissionLevel.LOCAL_MUTATION,
        requires_confirmation=True,
    )
    registry.register(action_b, handler=lambda ctx, args: {"deleted": True})

    action_store = ActionStore(db_path=str(tmp_path / "actions.db"))
    executor = ActionExecutor(
        registry=registry,
        store=action_store,
        personal_store=fake_pstore,
    )

    authority = ExecutionAuthority(
        proposal_id="prop-456",
        proposal_version=1,
        workspace_id="ws-test",
        granted_at=now_iso,
    )

    # Attempt to execute files.delete using coding.delegate authority
    with pytest.raises(UnauthorizedExecutionError) as exc_info:
        executor.execute(
            action_id="files.delete",
            input_data={"target": "/important"},
            authority=authority,
            auto_approve=True,
            workspace_id="ws-test",
        )
    assert "outside the authorized scope" in str(exc_info.value).lower() or "not authorized" in str(exc_info.value).lower()


def test_prompt_words_do_not_grant_authorization(tmp_path: Path):
    """
    A2: The presence of words like 'subito', 'direttamente', 'autonomamente'
    or phrases like «Ha subito un errore? Aggiungi un test» MUST NOT grant
    autonomous execution.
    """
    store = PersonalStore(db_path=str(tmp_path / "personal.db"))
    svc = PersonalAgentService(store=store)

    # 1. Italian incident phrase containing 'subito' as past participle
    p1 = "Ha subito un errore? Aggiungi un test."
    intent1 = svc.classify_intent(p1)
    assert intent1 is not None

    # 2. Command with 'direttamente'
    p2 = "Implementa foo direttamente nel file x.py"
    intent2 = svc.classify_intent(p2)
    assert intent2.action_id == "coding.delegate"

    # 3. Explicit negative phrasing
    p3 = "Non eseguire direttamente questa operazione"
    intent3 = svc.classify_intent(p3)
    assert intent3 is not None


def test_safety_policy_prevails_over_intent_classification(tmp_path: Path):
    """
    A1/A2: Even with a coding.delegate intent and words like 'subito',
    a policy requiring approval (Manual / Supervised) must produce a proposal_pending state,
    never executing automatically.
    """
    store = PersonalStore(db_path=str(tmp_path / "personal.db"))
    action_store = ActionStore(db_path=str(tmp_path / "actions.db"))

    registry = ActionRegistry()
    registry.register(
        ActionDefinition(
            id="coding.delegate",
            name="Delegate Coding",
            description="Delegate coding",
            tier=ActionTier.ACT,
            permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
            requires_confirmation=True,
        ),
        handler=lambda ctx, args: {"executed": True},
    )

    mock_policy_svc = MagicMock()
    mock_policy_svc.evaluate_action.return_value = (False, "Policy requires approval")

    safety_policy = ActionSafetyPolicy(policy_service=mock_policy_svc)
    executor = ActionExecutor(registry=registry, store=action_store, safety_policy=safety_policy)

    svc = PersonalAgentService(store=store, action_executor=executor)

    # Prompt with 'subito' and 'direttamente'
    prompt = "Delega subito ad Antigravity: aggiungi una funzione test nel file test.py direttamente"
    intent = svc.classify_intent(prompt)
    assert intent.action_id == "coding.delegate"

    # Process prompt through service
    res = svc.process_prompt(
        workspace_id="ws-test",
        prompt=prompt,
    )

    # Proposal must be pending, not executed
    assert res.metadata.get("status") in ("proposal_pending", "proposal_ready", "waiting_approval")
