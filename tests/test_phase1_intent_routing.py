"""
Phase 1: targeted routing regressions reproduced by the audit. Pure classification: no execution,
no providers, no network. Operational routing must never carry or grant consent.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from aether.personal.models import IntentTier, PersonalMessage
from aether.personal.service import PersonalAgentService, generate_executive_mandate


@pytest.fixture(scope="module")
def service():
    logging.disable(logging.CRITICAL)
    svc = PersonalAgentService(workspace=MagicMock(), store=MagicMock())
    yield svc
    logging.disable(logging.NOTSET)


def msg(role: str, content: str) -> PersonalMessage:
    return PersonalMessage(
        id=f"m-{role}", session_id="s", workspace_id="w", role=role, content=content, tier=IntentTier.ANSWER,
        steps=[], action_execution_id=None, mission_id=None, metadata={}, created_at="2026-01-01T00:00:00Z",
    )


HISTORY = [
    msg("user", "Aggiungi una funzione somma a /private/tmp/proj/calc.py"),
    msg("assistant", "Ho predisposto la delega. Verifica e conferma."),
]


@pytest.mark.parametrize("prompt", [
    "Implementa un'applicazione CLI per gestire le note nel repository /tmp/notes",
    "Crea una piccola applicazione Python chiamata FocusList nel progetto locale /tmp/focus",
    "Aggiungi una funzione somma a calc.py",
    "Risolvi il bug in calculator.py",
    "Fai refactoring del modulo parser.py",
    "Crea un nuovo script Python per rinominare i file in /tmp/demo",
])
def test_real_implementation_requests_route_to_coding(service, prompt):
    intent = service.classify_intent(prompt)
    assert intent.tier == IntentTier.ACT and intent.action_id == "coding.delegate"


@pytest.mark.parametrize("prompt", [
    "Cosa significa refactor?",
    "Che cosa fa la parola implement in Python?",
    "Spiegami cosa fa implement in questo codice",
    "Qual è la differenza tra Codex e Claude Code?",
    "Secondo te Codex è meglio di Claude per scrivere test sul mio file?",
    "Devo implementare una nuova funzione di pagamento, che ne pensi?",
    "Usa Codex per spiegarmi come funziona il file main.py",
    "Non modificare nulla, dimmi solo cosa cambieresti in auth.py",
])
def test_informational_questions_stay_informational(service, prompt):
    intent = service.classify_intent(prompt)
    assert intent.tier == IntentTier.ANSWER and not intent.action_id


@pytest.mark.parametrize("prompt", [
    "Crea un progetto per organizzare il mio viaggio a Roma",
    "Sviluppa un piano di studio per l'esame",
    "Crea un servizio di pulizia settimanale per la casa",
])
def test_creation_verbs_alone_do_not_make_a_coding_task(service, prompt):
    intent = service.classify_intent(prompt)
    assert intent.action_id != "coding.delegate"  # may be a plain answer or a workforce task, never a coding agent run


@pytest.mark.parametrize("followup", [
    "ok ma aspetta, non adesso",
    "va bene ma prima dimmi i rischi",
    "esegui pure ma solo dopo che ho controllato",
    "ok procedi ma non toccare i test",
    "sì però cambia il nome della funzione",
    "no",
    "non adesso",
])
def test_hedged_or_negative_followups_are_not_consent(service, followup):
    intent = service.classify_intent(followup, recent_history=HISTORY)
    assert intent.tier == IntentTier.ANSWER and not intent.action_id


def test_operational_routing_never_carries_consent(service):
    intent = service.classify_intent("Aggiungi una funzione somma a calc.py subito, direttamente, autonomamente")
    assert intent.action_id == "coding.delegate"
    assert "auto_approve" not in (intent.action_args or {})
    assert not any("approv" in k.lower() or "consent" in k.lower() for k in (intent.action_args or {}))


def test_executive_mandate_is_idempotent():
    once = generate_executive_mandate("Aggiungi la funzione somma")
    assert generate_executive_mandate(once) == once
    assert once.count("MANDATO ESECUTIVO") == 1


# --- ambiguity: deterministic contract + advisory LLM that can never upgrade or grant --------------

class FakeLLM:
    def __init__(self, content):
        self.content = content
        self.calls = 0

    def generate(self, messages, **kw):
        if "Classify the user" in messages[0].content:  # only the advisory verdict counts, not detail enrichment
            self.calls += 1
        return type("R", (), {"content": self.content})()


def svc_with(llm):
    return PersonalAgentService(workspace=MagicMock(), store=MagicMock(), provider=llm)


AMBIGUOUS = "Magari potremmo aggiungere una funzione somma a calc.py?"


def test_ambiguous_prompt_is_not_operational_without_an_llm(service):
    from aether.personal.intent_rules import assess_coding_prompt
    a = assess_coding_prompt(AMBIGUOUS)
    assert a.ambiguous and not a.operational
    assert service.classify_intent(AMBIGUOUS).tier == IntentTier.ANSWER


def test_llm_can_confirm_an_ambiguous_request_but_the_result_still_carries_no_consent():
    intent = svc_with(FakeLLM('{"intent": "operational"}')).classify_intent(AMBIGUOUS)
    assert intent.action_id == "coding.delegate"
    assert "auto_approve" not in (intent.action_args or {})


@pytest.mark.parametrize("answer", ['{"intent": "informational"}', '{"intent": "unclear"}', "no json at all", ""])
def test_llm_doubt_or_garbage_resolves_to_the_safe_side(answer):
    assert svc_with(FakeLLM(answer)).classify_intent(AMBIGUOUS).tier == IntentTier.ANSWER


def test_llm_is_never_consulted_for_clear_cases_and_cannot_upgrade_them():
    llm = FakeLLM('{"intent": "operational"}')
    svc = svc_with(llm)
    assert svc.classify_intent("Cosa significa refactor?").tier == IntentTier.ANSWER
    assert svc.classify_intent("Aggiungi una funzione somma a calc.py").action_id == "coding.delegate"
    assert llm.calls == 0


def test_polite_request_is_operational_not_ambiguous(service):
    assert service.classify_intent("Puoi aggiungere una funzione somma a calc.py?").action_id == "coding.delegate"


@pytest.mark.parametrize("prompt", [
    "Implement parser in /tmp/mock_project_repo",
    "Refactor files in /Library",
    "Please fix the login flow in /Users/dev/app",
])
def test_imperative_verb_with_a_concrete_location_is_a_work_order(service, prompt):
    assert service.classify_intent(prompt).action_id == "coding.delegate"


@pytest.mark.parametrize("prompt", [
    "Come funziona implement in /usr/bin?",
    "What does refactor mean in /etc/hosts context?",
    "Spiegami cosa significa fix in /tmp",
])
def test_questions_that_mention_a_location_stay_informational(service, prompt):
    assert service.classify_intent(prompt).action_id != "coding.delegate"
