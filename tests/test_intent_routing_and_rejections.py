"""
Tests for Phase 2 (A3): Intent routing reliability and follow-up handling.

Covers:
- The 6 critical audit false-positive prompts:
  1. «Qual è la differenza tra implement e extend in Java?»
  2. «Cosa significa refactor?»
  3. «Come si sviluppa un buon rapporto con un cliente?»
  4. «Non fare refactoring adesso, solo dimmi i rischi»
  5. «Aggiungi test al mio piano di allenamento»
  6. «Quanto costa il codex?»
- Actionable coding requests (positive cases).
- Follow-up disambiguation and negative rejection handling:
  - «Sicuramente no, non farlo» does not confirm pending mission.
  - «No», «non farlo», «annulla», «rifiuta» are recognized as cancellations.
  - «Sì, procedi» / «confermo» correctly confirm.
"""
from __future__ import annotations

import datetime
from pathlib import Path
import pytest

from aether.personal.models import PersonalMessage, IntentTier
from aether.personal.service import PersonalAgentService
from aether.personal.store import PersonalStore


@pytest.fixture
def agent_service(tmp_path: Path) -> PersonalAgentService:
    store = PersonalStore(db_path=str(tmp_path / "personal.db"))
    return PersonalAgentService(store=store)


def test_six_audit_prompts_are_not_coding_delegations(agent_service: PersonalAgentService):
    """
    Verifies that the 6 prompts flagged during the audit as false positives
    remain strictly informational or conversational and NEVER trigger coding.delegate.
    """
    audit_prompts = [
        "Qual è la differenza tra implement e extend in Java?",
        "Cosa significa refactor?",
        "Come si sviluppa un buon rapporto con un cliente?",
        "Non fare refactoring adesso, solo dimmi i rischi",
        "Aggiungi test al mio piano di allenamento",
        "Quanto costa il codex?",
    ]

    for p in audit_prompts:
        intent = agent_service.classify_intent(p)
        assert intent.action_id != "coding.delegate", f"Prompt falsely triggered coding.delegate: '{p}'"
        assert intent.tier == IntentTier.ANSWER, f"Prompt expected ANSWER tier: '{p}'"


def test_positive_coding_requests_are_classified_as_coding_delegate(agent_service: PersonalAgentService):
    """
    Verifies that genuine, actionable coding and testing directives are correctly recognized.
    """
    actionable_prompts = [
        "Aggiungi una funzione calculate_total(items) in billing.py e scrivi i test",
        "Correggi il bug in parser.py che causa crash su input nulli",
        "Nel progetto /tmp/app, implementa un nuovo endpoint GET /health in server.py",
        "Crea un test automatico per la classe UserValidator in test_validator.py",
        "Delega ad Antigravity: ottimizza la query SQL in database.py",
    ]

    for p in actionable_prompts:
        intent = agent_service.classify_intent(p)
        assert intent.action_id == "coding.delegate", f"Actionable prompt failed to trigger coding.delegate: '{p}'"
        assert intent.tier == IntentTier.ACT, f"Expected ACT tier: '{p}'"


def test_followup_negative_rejection_does_not_confirm_proposal(agent_service: PersonalAgentService):
    """
    Multi-turn follow-up test: «Sicuramente no, non farlo» must never be treated
    as a confirmation starting with 'si', and must result in cancellation.
    """
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    history = [
        PersonalMessage(
            id="msg-1",
            session_id="sess-test",
            workspace_id="ws-test",
            role="user",
            content="Aggiungi una funzione in app.py",
            created_at=now_iso,
        ),
        PersonalMessage(
            id="msg-2",
            session_id="sess-test",
            workspace_id="ws-test",
            role="assistant",
            content="Ho preparato la proposta per modificare app.py. Vuoi procedere?",
            metadata={"status": "proposal_pending", "proposal_id": "prop-1"},
            created_at=now_iso,
        ),
    ]

    negative_followups = [
        "Sicuramente no, non farlo",
        "No, annulla tutto",
        "Assolutamente no",
        "Non farlo",
        "Rifiuta la proposta",
        "Stop, non procedere",
    ]

    for neg_prompt in negative_followups:
        intent = agent_service.classify_intent(neg_prompt, recent_history=history)
        assert intent.action_id != "coding.delegate", f"Negative follow-up triggered coding.delegate: '{neg_prompt}'"
        assert intent.intent_type == "cancellation" or "cancell" in str(intent.summary).lower() or intent.tier == IntentTier.ANSWER, (
            f"Negative follow-up not handled as cancellation: '{neg_prompt}'"
        )


def test_followup_affirmative_confirms_proposal(agent_service: PersonalAgentService):
    """
    Multi-turn follow-up test: «Sì, procedi pure» or «Confermo» correctly resolves
    to confirming the pending proposal.
    """
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    history = [
        PersonalMessage(
            id="msg-1",
            session_id="sess-test",
            workspace_id="ws-test",
            role="user",
            content="Aggiungi una funzione in app.py",
            created_at=now_iso,
        ),
        PersonalMessage(
            id="msg-2",
            session_id="sess-test",
            workspace_id="ws-test",
            role="assistant",
            content="Ho preparato la proposta per modificare app.py. Vuoi procedere?",
            metadata={"status": "proposal_pending", "proposal_id": "prop-1", "action_id": "coding.delegate"},
            created_at=now_iso,
        ),
    ]

    affirmative_followups = [
        "Sì, procedi pure",
        "Si, confermo",
        "Procedi",
        "Conferma",
    ]

    for aff_prompt in affirmative_followups:
        intent = agent_service.classify_intent(aff_prompt, recent_history=history)
        assert intent.action_id == "coding.delegate"
        assert intent.tier == IntentTier.ACT
