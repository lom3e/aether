"""Aether takes the initiative on what you tell it: "Rossi vuole il preventivo entro venerdì" becomes one confirmation
(add Rossi to clients, note the quote with its due date), saved only after you accept, and undoable."""
from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

from aether.actions import undo as undo_mod
from aether.actions.registry import ActionRegistry
import aether.core.context as context_mod
from aether.life.store import life_store_for
from aether.personal import tool_router
from aether.workspace.workspace import Workspace

NOW = dt.datetime(2026, 10, 22, 10, 0).astimezone()


class Model:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def generate(self, messages):
        self.calls += 1
        return SimpleNamespace(content=self.payload if isinstance(self.payload, str) else json.dumps(self.payload))


def test_router_reads_a_commitment_and_refuses_an_incomplete_one():
    assert tool_router.worth_routing("Rossi vuole il preventivo entro venerdì")
    assert tool_router.worth_routing("ricordami di chiamare il commercialista domani")
    r = tool_router.route("Rossi vuole il preventivo entro venerdì", now=NOW, provider=Model(
        {"action": "life_note", "note_kind": "job", "title": "Inviare il preventivo", "contact_name": "Rossi", "due": "2026-10-24"}))
    assert r["action"] == "life_note" and r["kind"] == "job" and r["contact_name"] == "Rossi" and not r["due_has_time"]
    # the model said Saturday 24; "venerdì" from Thursday 22 is Friday 23, whatever the model counted
    assert dt.datetime.fromtimestamp(r["due_at"]).astimezone().strftime("%Y-%m-%d %H:%M") == "2026-10-23 09:00"
    rem = tool_router.route("ricordami alle 10", now=NOW, provider=Model({"action": "life_note", "note_kind": "reminder", "title": "Chiamare il commercialista", "due": "2026-10-23T10:00"}))
    assert rem["kind"] == "reminder" and rem["due_has_time"]
    assert tool_router.route("x", now=NOW, provider=Model({"action": "life_note", "note_kind": "job", "title": ""}))["action"] == "none"
    assert tool_router.route("x", now=NOW, provider=Model({"action": "life_note", "note_kind": "contact", "contact_name": ""}))["action"] == "none"
    assert tool_router.route("x", now=NOW, provider=Model({"action": "life_note", "note_kind": "payment", "title": "x"}))["action"] == "none"


def test_the_save_action_is_registered_and_needs_confirmation():
    d = ActionRegistry().get("life.save")
    assert d is not None and d.requires_confirmation and d.tier.value == "act"


def test_the_model_is_told_to_offer_not_to_lecture():
    text = open(context_mod.__file__, encoding="utf-8").read()
    assert "Sii intraprendente" in text and "Non ho eseguito" in text  # the old opening is named only to forbid it
    assert "indica la frase con cui chiederla" not in text


def _friday_9() -> dt.datetime:
    """09:00 wall-clock on the next Friday after today (the prompts say "venerdì"; right across a daylight-saving change)."""
    day = dt.date.today() + dt.timedelta(days=(4 - dt.date.today().weekday()) % 7 or 7)
    return dt.datetime(day.year, day.month, day.day, 9, 0).astimezone()


def test_a_sentence_becomes_one_confirmation_then_a_client_and_a_job_and_undo_takes_both_back(tmp_path):
    ws = Workspace.init(tmp_path, name="life-chat")
    try:
        svc = ws.personal
        due = _friday_9()
        svc._router_provider_override = Model({"action": "life_note", "note_kind": "job", "title": "Inviare il preventivo",
                                               "contact_name": "Rossi", "due": due.strftime("%Y-%m-%d")})
        store = life_store_for(ws)
        msg = svc.process_prompt(workspace_id=ws.name, prompt="Rossi vuole il preventivo entro venerdì")
        assert msg.metadata["status"] == "proposal_pending"
        assert "Aggiungo **Rossi** ai clienti e segno **Inviare il preventivo** entro" in msg.content
        assert "Non ho eseguito" not in msg.content and "Non salvo niente finché non confermi" in msg.content
        assert store.list_contacts() == [] and store.list_jobs() == [], "nothing is saved before the user confirms"
        assert msg.metadata["resolved_action"]["action_id"] == "life.save"

        _, authority = svc.accept_proposal(proposal_id=msg.metadata["proposal_id"], workspace_id=ws.id,
                                           expected_version=msg.metadata["proposal_version"], actor="user", channel="api")
        done = svc.process_prompt(workspace_id=ws.name, prompt="Rossi vuole il preventivo entro venerdì", session_id=msg.session_id, authority=authority)
        assert done.content.startswith("Fatto: ho aggiunto **Rossi** ai clienti e ho segnato **Inviare il preventivo** entro"), done.content
        contacts, jobs = store.list_contacts(), store.list_jobs()
        assert [c["name"] for c in contacts] == ["Rossi"] and contacts[0]["kind"] == "client"
        assert [j["title"] for j in jobs] == ["Inviare il preventivo"] and jobs[0]["contact_id"] == contacts[0]["id"]
        assert abs(jobs[0]["due_at"] - due.timestamp()) < 1
        mem = ws.memory.get_memory(store.get_job(jobs[0]["id"])["memory_id"], workspace_id=ws.id)
        assert mem and "Lavoro per Rossi" in mem.summary, "what Aether knows reads in Italian"

        exec_id = done.metadata["undo_execution_id"]
        item = undo_mod.describe(ws, ws.action_store.get_execution(exec_id))
        assert item["reversible"] and item["kind"] == "remove_note"
        undo_mod.undo(ws, exec_id)
        assert store.list_jobs() == [] and store.list_contacts() == [], "undo takes back the job and the client it created"
    finally:
        ws.close()


def test_an_existing_client_is_reused_and_a_missing_due_date_is_asked_for(tmp_path):
    ws = Workspace.init(tmp_path, name="life-chat-2")
    try:
        svc = ws.personal
        store = life_store_for(ws)
        store.add_contact("Mario Rossi", kind="client")
        svc._router_provider_override = Model({"action": "life_note", "note_kind": "job", "title": "Inviare il preventivo", "contact_name": "Mario Rossi", "due": ""})
        msg = svc.process_prompt(workspace_id=ws.name, prompt="devo fare il preventivo a Mario Rossi")
        assert "Segno per **Mario Rossi** **Inviare il preventivo**" in msg.content and "ai clienti" not in msg.content
        assert "Non c'è una scadenza" in msg.content
    finally:
        ws.close()


def test_yes_after_an_offer_turns_the_offer_into_the_confirmation(tmp_path):
    ws = Workspace.init(tmp_path, name="life-chat-3")
    try:
        svc = ws.personal
        offer = Model({"action": "none"})
        svc._router_provider_override = offer
        first = svc.process_prompt(workspace_id=ws.name, prompt="ciao")
        # the assistant offered something (as the prompt now asks it to); the user says yes
        svc.store.add_message(type(first)(id="msg-offer", session_id=first.session_id, workspace_id=first.workspace_id, role="assistant",
                                          content="Vuoi che aggiunga Rossi ai clienti e segni il preventivo per venerdì?",
                                          created_at=dt.datetime.now(dt.timezone.utc).isoformat()))
        svc._router_provider_override = Model({"action": "life_note", "note_kind": "job", "title": "Inviare il preventivo", "contact_name": "Rossi", "due": _friday_9().strftime("%Y-%m-%d")})
        yes = svc.process_prompt(workspace_id=ws.name, prompt="sì, fallo", session_id=first.session_id)
        assert yes.metadata.get("status") == "proposal_pending" and "Aggiungo **Rossi** ai clienti" in yes.content
    finally:
        ws.close()


def test_a_reminder_never_creates_a_client(tmp_path):
    ws = Workspace.init(tmp_path, name="life-chat-4")
    try:
        svc = ws.personal
        svc._router_provider_override = Model({"action": "life_note", "note_kind": "reminder", "title": "Chiamare il commercialista",
                                               "contact_name": "commercialista", "due": _friday_9().strftime("%Y-%m-%dT10:00")})
        msg = svc.process_prompt(workspace_id=ws.name, prompt="ricordami di chiamare il commercialista venerdì alle 10")
        assert msg.content.startswith("Ti ricordo **Chiamare il commercialista**") and "alle 10:00" in msg.content and "ai clienti" not in msg.content
    finally:
        ws.close()
