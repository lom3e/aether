"""A reply may never say that something was done in the real world when no action ran in that turn."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from aether.core.execution import ExecutionStatus
from aether.personal.service import claims_unexecuted_action, honest_no_action_reply
from aether.workspace.workspace import Workspace


@pytest.mark.parametrize("text", [
    "Certo, provvedo subito a rimuovere l'appuntamento dal tuo calendario.",
    "Ho cancellato l'evento di domani.",
    "Devo delegare l'operazione al manager interno, ti farò sapere.",
    "Fatto! Ho inviato la mail a Marco.",
    "I've deleted the meeting from your calendar.",
    "I'll send it now.",
])
def test_claims_are_caught(text):
    assert claims_unexecuted_action(text)


@pytest.mark.parametrize("text,prompt", [
    ("Ecco i tuoi impegni di domani.", "che impegni ho domani?"),
    ("Per cancellare un evento scrivi: cancella \"Titolo\".", "come cancello un evento?"),
    ("Il preventivo è stato inviato ieri da Marco.", "quando è stato inviato il preventivo?"),
    ("Ciao Marco, ho inviato il preventivo questa mattina.", "scrivimi una mail per Marco"),
    ("Puoi rispondere così: «ho cancellato la riunione».", "come rispondo al cliente?"),
])
def test_ordinary_text_and_drafts_are_left_alone(text, prompt):
    assert not claims_unexecuted_action(text, prompt)


def test_the_honest_reply_follows_the_language():
    assert "Non ho eseguito nessuna azione" in honest_no_action_reply("x", "cancellalo")
    assert "I haven't done anything" in honest_no_action_reply("x", "please delete my meeting")


def test_the_real_chat_path_replaces_a_fake_claim(tmp_path, monkeypatch):
    ws = Workspace.init(tmp_path, name="honesty")
    try:
        fake = SimpleNamespace(status=ExecutionStatus.COMPLETED, output="Certo, provvedo subito a spostare la riunione a venerdì.", error=None, metadata={})
        monkeypatch.setattr(ws.personal.runtime, "execute", lambda *a, **k: fake)
        msg = ws.personal.process_prompt(workspace_id=ws.name, prompt="quella cosa con Rossi spostala a dopo")
        assert msg.action_execution_id is None
        assert "provvedo" not in msg.content and "Non ho eseguito nessuna azione" in msg.content
        assert msg.metadata.get("honesty_guard") == "unexecuted_action_claim"
    finally:
        ws.close()
