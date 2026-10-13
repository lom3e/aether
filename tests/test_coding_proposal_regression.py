import pytest
from pathlib import Path
import tempfile
from aether.personal.service import PersonalAgentService
from aether.personal.store import PersonalStore
from aether.planning.contracts import ProposalStatus


def test_coding_delegation_intent_and_proposal_regression():
    """
    Regression test verifying that a coding delegation request with an absolute project path
    and explicit files:
    1. Preserves exact casing of the path in the title and narrative.
    2. Correctly matches the existing repository and files on disk.
    3. Produces READY_FOR_ACCEPTANCE (not NEEDS_CLARIFICATION).
    4. Only requires coding.delegate approval (no phantom pull request approvals).
    5. Does not inject unrequested pull_request_created outcome constraints.
    """
    tmp_db = tempfile.mktemp(suffix=".db")
    store = PersonalStore(db_path=tmp_db)
    svc = PersonalAgentService(store=store)

    prompt = (
        "Nel progetto locale /tmp/aether-manual-gate-8b5cFo, aggiungi una funzione subtract(a, b) "
        "in calculator.py che restituisca a - b, e aggiungi un test corrispondente in test_calculator.py. "
        "Delega il lavoro a Google Antigravity. Prepara prima la proposta e mostra chiaramente il provider "
        "designato e il progetto di destinazione. Non modificare i file e non avviare l'esecuzione finché "
        "non avrò approvato esplicitamente la proposta. Non modificare altri file."
    )

    classified = svc.classify_intent(prompt)
    assert classified.action_id == "coding.delegate"
    assert classified.action_args.get("provider_id") == "antigravity"
    assert "calculator.py" in classified.action_args.get("context_files", [])
    assert "test_calculator.py" in classified.action_args.get("context_files", [])

    intent, context, prop, val = svc.create_intent_and_proposal(prompt, workspace_id="default")

    # 1. Path casing preserved in title
    assert "8b5cFo" in prop.title
    assert "8b5cfo" not in prop.title

    # 2. Status is ready_for_acceptance
    assert prop.status == ProposalStatus.READY_FOR_ACCEPTANCE
    assert prop.confidence >= 0.8
    assert len(context.unresolved_references) == 0

    # 3. Only coding.delegate approval, no github PR approval
    approvals = [a.action_or_boundary for a in prop.required_approvals]
    assert "coding.delegate" in approvals
    assert "github.create_pull_request" not in approvals

    # 4. No phantom PR outcome constraints
    outcomes = [c.kind for c in prop.outcome_constraints]
    assert "deliverable_created" in outcomes
    assert "pull_request_created" not in outcomes
