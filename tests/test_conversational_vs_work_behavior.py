"""
Regression test suite for Conversational vs Operational Work behavior.
Ensures adherence to the Permanent UX Principle:
'Tu dimmi cosa vuoi ottenere. Aether si occupa del resto.'
Verifies that:
1. Casual conversation & greetings ('Ciao', 'Grazie') do NOT generate missions or operational steps.
2. Informational questions ('Che cosa puoi fare per me?') provide clear answers without mission overhead.
3. Simple queries needing real data ('Che appuntamenti ho domani?') execute calendar queries directly.
4. Complex work requests ('Analizza il progetto Alfa...') generate structured proposals without fake completions.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from aether.personal.models import IntentTier
from aether.workspace.workspace import Workspace


@pytest.fixture
def temp_workspace_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def workspace(temp_workspace_dir):
    ws = Workspace.init(temp_workspace_dir, name="test_conv_ws")
    yield ws
    ws.close()


def test_casual_conversation_greetings_produce_no_operational_steps(workspace):
    """Greeting 'Ciao' must produce natural response with ZERO operational steps and NO missions."""
    personal_svc = workspace.personal

    # Test 'Ciao'
    res_ciao = personal_svc.process_prompt(
        workspace_id=workspace.name,
        prompt="Ciao",
    )
    assert res_ciao.role == "assistant"
    assert res_ciao.tier == IntentTier.ANSWER
    assert res_ciao.metadata.get("intent_type") == "conversation"
    assert len(res_ciao.steps) == 0, f"Expected 0 steps for casual greeting, got {len(res_ciao.steps)}"
    assert res_ciao.action_execution_id is None
    assert res_ciao.mission_id is None
    assert workspace.missions.list_missions() == []
    # Content must not be empty
    assert len(res_ciao.content.strip()) > 0

    # Test 'Grazie'
    res_grazie = personal_svc.process_prompt(
        workspace_id=workspace.name,
        prompt="Grazie",
    )
    assert res_grazie.role == "assistant"
    assert res_grazie.tier == IntentTier.ANSWER
    assert res_grazie.metadata.get("intent_type") == "conversation"
    assert len(res_grazie.steps) == 0
    assert workspace.missions.list_missions() == []


def test_informational_inquiry_does_not_create_mission(workspace):
    """'Che cosa puoi fare per me?' must explain capabilities without creating missions or actions."""
    personal_svc = workspace.personal

    res = personal_svc.process_prompt(
        workspace_id=workspace.name,
        prompt="Che cosa puoi fare per me?",
    )
    assert res.role == "assistant"
    assert res.tier == IntentTier.ANSWER
    assert res.metadata.get("intent_type") == "informational"
    assert res.action_execution_id is None
    assert res.mission_id is None
    assert workspace.missions.list_missions() == []
    assert len(res.content.strip()) > 0


def test_calendar_query_uses_real_connector_without_mission(workspace):
    """'Che appuntamenti ho domani?' must execute calendar.list_events and return truthful status."""
    personal_svc = workspace.personal

    intent = personal_svc.classify_intent("Che appuntamenti ho domani?")
    assert intent.tier == IntentTier.ANSWER
    assert intent.action_id == "calendar.list_events"
    assert intent.action_args.get("scope") == "tomorrow"

    res = personal_svc.process_prompt(
        workspace_id=workspace.name,
        prompt="Che appuntamenti ho domani?",
    )
    assert res.role == "assistant"
    assert res.tier == IntentTier.ANSWER
    # Check that it executed the real action and answered truthfully
    assert any("calendar" in s.title.lower() or "action" in s.category for s in res.steps)
    assert "domani" in res.content.lower()
    # No mission was created
    assert workspace.missions.list_missions() == []


def test_complex_request_routes_to_delegation_proposal(workspace):
    """'Analizza il progetto Alfa e dimmi cosa non va.' must route to DELEGATE and produce a proposal."""
    personal_svc = workspace.personal

    intent = personal_svc.classify_intent("Analizza il progetto Alfa e dimmi cosa non va.")
    assert intent.tier == IntentTier.DELEGATE

    res = personal_svc.process_prompt(
        workspace_id=workspace.name,
        prompt="Analizza il progetto Alfa e dimmi cosa non va.",
    )
    assert res.tier == IntentTier.DELEGATE
    assert res.metadata.get("status") == "proposal_pending"
    proposal_data = res.metadata.get("proposal")
    assert proposal_data is not None
    assert proposal_data["status"] == "needs_clarification"
    # Clarification regarding Alfa must be present
    assert any("Alfa" in q.get("question", "") for q in proposal_data.get("clarification_requirements", []))
