"""Earned autonomy: after three approvals of the same narrow kind of change Aether offers to do it alone; once the user
grants it, that kind runs without a card (still in Rewind, still undoable); an Undo restarts the count; sending mail is
never eligible and nothing the user did not allow runs alone."""
from __future__ import annotations

import json
from types import SimpleNamespace

from aether.actions import undo as undo_mod
from aether.personal.autonomy import AutonomyStore, autonomy_store_for, key_for
from aether.workspace.workspace import Workspace


class Model:
    def __init__(self, payload):
        self.payload = payload

    def generate(self, messages):
        return SimpleNamespace(content=json.dumps(self.payload))


class FakeGmail:
    def __init__(self):
        self.trashed: list[str] = []

    def can_change_mail(self):
        return True

    def search(self, query="in:inbox", limit=10):
        return [{"id": f"z{len(self.trashed)}", "from": "Zalando", "subject": "Saldi", "date": ""}]

    def trash(self, ids):
        self.trashed += ids
        return list(ids)

    def untrash(self, ids):
        return list(ids)


def test_keys_are_narrow_and_sending_is_never_eligible(tmp_path):
    assert key_for("gmail.trash", {"query": "from:Zalando ", "op": "trash"}) == "gmail.trash|trash|from:zalando"
    assert key_for("gmail.trash", {"query": ""}) is None
    assert key_for("gmail.send", {"to": "x"}) is None and key_for("google_calendar.delete_event", {}) is None
    st = AutonomyStore(tmp_path / "a.db")
    assert st.note_approved("k", "x") is None and st.note_approved("k", "x") is None
    offer = st.note_approved("k", "x")
    assert offer == {"key": "k", "label": "x", "count": 3}
    assert st.note_approved("k", "x") is None, "offered once"
    st.decide("k", True)
    assert st.granted("k") and st.revoke("k") and not st.granted("k")


def _wire(ws, monkeypatch, gmail):
    svc = ws.personal
    monkeypatch.setattr(svc, "_provider_ready", lambda ws_id, prov: True)
    monkeypatch.setattr(ws.connections, "get_gmail_connector", lambda ws_id: gmail)
    svc._router_provider_override = Model({"action": "mail_trash", "mail_query": "from:zalando"})
    return svc


def _ask_and_accept(svc, ws, prompt, session_id=None):
    msg = svc.process_prompt(workspace_id=ws.name, prompt=prompt, session_id=session_id)
    assert msg.metadata.get("status") == "proposal_pending", msg.content
    _, authority = svc.accept_proposal(proposal_id=msg.metadata["proposal_id"], workspace_id=ws.id,
                                       expected_version=msg.metadata["proposal_version"], actor="user", channel="api")
    return svc.process_prompt(workspace_id=ws.name, prompt=prompt, session_id=msg.session_id, authority=authority)


def test_three_approvals_offer_autonomy_then_it_runs_alone_and_undo_still_works(tmp_path, monkeypatch):
    ws = Workspace.init(tmp_path, name="autonomy")
    try:
        gmail = FakeGmail()
        svc = _wire(ws, monkeypatch, gmail)
        prompt = "elimina le mail di Zalando"
        first = _ask_and_accept(svc, ws, prompt)
        assert "autonomy_offer" not in first.metadata
        _ask_and_accept(svc, ws, prompt, first.session_id)
        third = _ask_and_accept(svc, ws, prompt, first.session_id)
        offer = third.metadata["autonomy_offer"]
        assert offer["key"] == "gmail.trash|trash|from:zalando" and "Zalando" in offer["label"].title()
        store = autonomy_store_for(ws)
        assert not store.granted(offer["key"]), "an offer is not a permission"

        store.decide(offer["key"], True)
        alone = svc.process_prompt(workspace_id=ws.name, prompt=prompt, session_id=first.session_id)
        assert alone.metadata.get("status") != "proposal_pending" and alone.metadata.get("done_alone") is True
        assert alone.content.startswith("Fatto da solo, come mi avevi permesso.") and len(gmail.trashed) == 4
        assert alone.metadata.get("undo_execution_id")

        # a different kind (another sender) still asks
        svc._router_provider_override = Model({"action": "mail_trash", "mail_query": "from:amazon"})
        other = svc.process_prompt(workspace_id=ws.name, prompt="elimina le mail di Amazon", session_id=first.session_id)
        assert other.metadata.get("status") == "proposal_pending"

        # revoked: it asks again
        store.revoke(offer["key"])
        svc._router_provider_override = Model({"action": "mail_trash", "mail_query": "from:zalando"})
        again = svc.process_prompt(workspace_id=ws.name, prompt=prompt, session_id=first.session_id)
        assert again.metadata.get("status") == "proposal_pending"

        # an Undo restarts the count for a kind not yet granted
        svc._router_provider_override = Model({"action": "mail_trash", "mail_query": "from:amazon"})
        a1 = _ask_and_accept(svc, ws, "elimina le mail di Amazon", first.session_id)
        _ask_and_accept(svc, ws, "elimina le mail di Amazon", first.session_id)
        undo_mod.undo(ws, a1.metadata["undo_execution_id"])
        a3 = _ask_and_accept(svc, ws, "elimina le mail di Amazon", first.session_id)
        assert "autonomy_offer" not in a3.metadata
    finally:
        ws.close()
