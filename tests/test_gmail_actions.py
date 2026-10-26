"""Gmail changes from chat: a reply or a new email becomes a DRAFT shown in full before it is saved (never sent), mail goes
to the Trash / archive / read only after a confirmation listing it, and every change has its exact Undo."""
from __future__ import annotations

import base64
import email
import json
from types import SimpleNamespace

from aether.actions import undo as undo_mod
from aether.actions.registry import ActionRegistry
from aether.connections.gmail import GMAIL_MODIFY_SCOPE, GmailConnector
from aether.personal import tool_router
from aether.workspace.workspace import Workspace


class Model:
    """Answers in order: first the routing JSON, then (for drafts) the written email."""

    def __init__(self, *payloads):
        self.payloads = list(payloads)

    def generate(self, messages):
        p = self.payloads.pop(0) if len(self.payloads) > 1 else self.payloads[0]
        return SimpleNamespace(content=p if isinstance(p, str) else json.dumps(p))


class FakeGmail:
    def __init__(self, writable=True):
        self.writable = writable
        self.drafts: dict[str, dict] = {}
        self.trashed: set[str] = set()
        self.labels = {"m1": {"INBOX", "UNREAD"}, "m2": {"INBOX", "UNREAD"}}
        self.mail = [{"id": "m1", "thread_id": "t1", "from": "Mario Rossi", "subject": "Preventivo sito", "date": "Thu, 22 Oct 2026"},
                     {"id": "m2", "thread_id": "t2", "from": "Zalando", "subject": "Saldi -50%", "date": "Wed, 21 Oct 2026"}]

    def can_change_mail(self):
        return self.writable

    def search(self, query="in:inbox", limit=10):
        if "zalando" in query.lower():
            return [m for m in self.mail if m["from"] == "Zalando"][:limit]
        if "rossi" in query.lower():
            return [m for m in self.mail if m["from"] == "Mario Rossi"][:limit]
        return []

    def reply_context(self, message_id):
        return {"id": message_id, "thread_id": "t1", "from_raw": "Mario Rossi <rossi@example.com>", "from": "Mario Rossi",
                "subject": "Preventivo sito", "message_id_header": "<abc@mail>", "references": "", "text": "Ciao, quando arriva il preventivo?"}

    def create_draft(self, **kw):
        did = f"d{len(self.drafts) + 1}"
        self.drafts[did] = kw
        return {"draft_id": did, "message_id": "x", "thread_id": kw.get("thread_id")}

    def draft_exists(self, draft_id):
        return draft_id in self.drafts

    def delete_draft(self, draft_id):
        self.drafts.pop(draft_id)

    def trash(self, ids):
        self.trashed |= set(ids)
        return list(ids)

    def untrash(self, ids):
        self.trashed -= set(ids)
        return list(ids)

    def modify_labels(self, ids, add=None, remove=None):
        for i in ids:
            self.labels[i] = (self.labels[i] | set(add or [])) - set(remove or [])


def test_only_safe_mail_actions_exist_and_all_need_confirmation():
    reg = ActionRegistry()
    for aid in ("gmail.create_draft", "gmail.send", "gmail.trash", "gmail.modify_labels"):
        d = reg.get(aid)
        assert d is not None and d.requires_confirmation and d.tier.value == "act"
    assert reg.get("gmail.delete") is None, "no permanent deletion"


def test_router_refuses_a_change_on_the_whole_inbox():
    for q in ("", "in:inbox", "*", "is:unread"):
        r = tool_router.route("cancella tutto", provider=Model({"action": "mail_trash", "mail_query": q}))
        assert r["action"] == "none", q
    assert tool_router.route("segna tutto come letto", provider=Model({"action": "mail_mark_read", "mail_query": "is:unread"}))["action"] == "mail_mark_read"
    assert tool_router.route("rispondi", provider=Model({"action": "mail_reply", "mail_query": "from:rossi", "instructions": ""}))["action"] == "none"


def test_the_connector_builds_a_threaded_draft_and_never_sends(monkeypatch):
    c = GmailConnector(auth_metadata={"access_token": "t", "scope": f"openid {GMAIL_MODIFY_SCOPE}"})
    calls = []
    monkeypatch.setattr(c, "_api_request", lambda endpoint, method="GET", params=None, data=None, **k: (calls.append((method, endpoint, data)), {"id": "d1", "message": {"id": "m9", "threadId": "t1"}})[1])
    out = c.create_draft(to="rossi@example.com", subject="Re: Preventivo", body="Arriva lunedì.", thread_id="t1", in_reply_to="<abc@mail>")
    method, endpoint, data = calls[0]
    assert (method, endpoint) == ("POST", "users/me/drafts") and data["message"]["threadId"] == "t1" and out["draft_id"] == "d1"
    raw = email.message_from_bytes(base64.urlsafe_b64decode(data["message"]["raw"]))
    assert raw["To"] == "rossi@example.com" and raw["In-Reply-To"] == "<abc@mail>" and "Arriva lunedì." in raw.get_payload(decode=True).decode()
    assert not [x for x in calls if "send" in x[1]]
    assert c.can_change_mail() and not GmailConnector(auth_metadata={"access_token": "t", "scope": "gmail.readonly"}).can_change_mail()


def _wire(ws, monkeypatch, fake):
    svc = ws.personal
    monkeypatch.setattr(svc, "_provider_ready", lambda ws_id, prov: True)
    monkeypatch.setattr(ws.connections, "get_gmail_connector", lambda ws_id: fake)
    return svc


def _accept(svc, ws, msg):
    _, authority = svc.accept_proposal(proposal_id=msg.metadata["proposal_id"], workspace_id=ws.id,
                                       expected_version=msg.metadata["proposal_version"], actor="user", channel="api")
    return svc.process_prompt(workspace_id=ws.name, prompt=msg.metadata.get("_prompt", ""), session_id=msg.session_id, authority=authority)


def test_a_reply_is_shown_in_full_saved_only_as_a_draft_and_undo_removes_it(tmp_path, monkeypatch):
    ws = Workspace.init(tmp_path, name="gmail-reply")
    try:
        fake = FakeGmail()
        svc = _wire(ws, monkeypatch, fake)
        svc._router_provider_override = Model({"action": "mail_reply", "mail_query": "from:rossi", "instructions": "il preventivo arriva lunedì"},
                                              {"subject": "x", "body": "Ciao Mario,\n\nil preventivo arriva lunedì.\n\nA presto"})
        prompt = "rispondi a Rossi che il preventivo arriva lunedì"
        msg = svc.process_prompt(workspace_id=ws.name, prompt=prompt)
        assert msg.metadata["status"] == "proposal_pending"
        assert "Ecco la risposta per **Mario Rossi**" in msg.content and "> il preventivo arriva lunedì." in msg.content
        assert "Re: Preventivo sito" in msg.content and "non la invio" in msg.content and fake.drafts == {}
        msg.metadata["_prompt"] = prompt
        done = _accept(svc, ws, msg)
        assert done.content.startswith("Fatto: la bozza per **Mario Rossi** è tra le bozze di Gmail. Non è stata inviata."), done.content
        (draft,) = fake.drafts.values()
        assert draft["to"] == "Mario Rossi <rossi@example.com>" and draft["thread_id"] == "t1" and draft["in_reply_to"] == "<abc@mail>"
        undo_mod.undo(ws, done.metadata["undo_execution_id"])
        assert fake.drafts == {}
    finally:
        ws.close()


def test_trash_lists_the_mail_first_and_undo_takes_it_back(tmp_path, monkeypatch):
    ws = Workspace.init(tmp_path, name="gmail-trash")
    try:
        fake = FakeGmail()
        svc = _wire(ws, monkeypatch, fake)
        svc._router_provider_override = Model({"action": "mail_trash", "mail_query": "from:zalando"})
        prompt = "elimina le mail di Zalando"
        msg = svc.process_prompt(workspace_id=ws.name, prompt=prompt)
        assert "Sposto nel cestino questa mail" in msg.content and "**Zalando** — Saldi -50%" in msg.content and "30 giorni" in msg.content
        assert fake.trashed == set()
        msg.metadata["_prompt"] = prompt
        done = _accept(svc, ws, msg)
        assert done.content.startswith("Fatto: ho spostato nel cestino 1 mail.") and fake.trashed == {"m2"}
        undo_mod.undo(ws, done.metadata["undo_execution_id"])
        assert fake.trashed == set()
    finally:
        ws.close()


def test_archive_and_its_exact_inverse(tmp_path, monkeypatch):
    ws = Workspace.init(tmp_path, name="gmail-archive")
    try:
        fake = FakeGmail()
        svc = _wire(ws, monkeypatch, fake)
        svc._router_provider_override = Model({"action": "mail_archive", "mail_query": "from:zalando"})
        msg = svc.process_prompt(workspace_id=ws.name, prompt="archivia le mail di Zalando")
        assert msg.content.startswith("Archivio questa mail")
        msg.metadata["_prompt"] = "archivia le mail di Zalando"
        done = _accept(svc, ws, msg)
        assert "INBOX" not in fake.labels["m2"]
        undo_mod.undo(ws, done.metadata["undo_execution_id"])
        assert "INBOX" in fake.labels["m2"] and "UNREAD" in fake.labels["m2"], "back exactly as it was"
    finally:
        ws.close()


def test_a_read_only_connection_asks_to_reconnect_and_changes_nothing(tmp_path, monkeypatch):
    ws = Workspace.init(tmp_path, name="gmail-ro")
    try:
        fake = FakeGmail(writable=False)
        svc = _wire(ws, monkeypatch, fake)
        svc._router_provider_override = Model({"action": "mail_trash", "mail_query": "from:zalando"})
        msg = svc.process_prompt(workspace_id=ws.name, prompt="elimina le mail di Zalando")
        assert "sola lettura" in msg.content and "Collegamenti" in msg.content and msg.metadata.get("status") != "proposal_pending"
        assert fake.trashed == set()
    finally:
        ws.close()


def test_a_new_email_uses_the_address_saved_for_the_person(tmp_path, monkeypatch):
    ws = Workspace.init(tmp_path, name="gmail-compose")
    try:
        from aether.life.store import life_store_for

        life_store_for(ws).add_contact("Bianchi", kind="client", email="bianchi@example.com")
        fake = FakeGmail()
        svc = _wire(ws, monkeypatch, fake)
        svc._router_provider_override = Model({"action": "mail_compose", "contact_name": "Bianchi", "instructions": "chiedi la fattura di ottobre"},
                                              {"subject": "Fattura di ottobre", "body": "Buongiorno,\n\npotrebbe inviarmi la fattura di ottobre?\n\nGrazie"})
        msg = svc.process_prompt(workspace_id=ws.name, prompt="scrivi a Bianchi per chiedere la fattura di ottobre")
        assert "Ecco la mail per **Bianchi**" in msg.content and "Fattura di ottobre" in msg.content
        assert msg.metadata["resolved_action"]["args"]["to"] == "bianchi@example.com"
        svc._router_provider_override = Model({"action": "mail_compose", "contact_name": "Verdi", "instructions": "ciao"})
        missing = svc.process_prompt(workspace_id=ws.name, prompt="scrivi a Verdi")
        assert "Non ho l'indirizzo email di **Verdi**" in missing.content
    finally:
        ws.close()


class SendingGmail(FakeGmail):
    def __init__(self):
        super().__init__()
        self.sent: list[str] = []

    def send_draft(self, draft_id):
        self.sent.append(draft_id)
        return {"message_id": "s1"}


def test_sending_waits_the_undo_window_and_undo_keeps_it_as_a_draft(tmp_path, monkeypatch):
    import time

    from aether.actions import mail_send

    ws = Workspace.init(tmp_path, name="gmail-send")
    try:
        fake = SendingGmail()
        svc = _wire(ws, monkeypatch, fake)
        monkeypatch.setattr(mail_send, "SEND_DELAY_SECONDS", 5.0)
        svc._router_provider_override = Model({"action": "mail_reply", "mail_query": "from:rossi", "instructions": "arriva lunedì", "send": "true"},
                                              {"subject": "x", "body": "Ciao Mario,\n\narriva lunedì.\n\nA presto"})
        prompt = "invia a Rossi una risposta: arriva lunedì"
        msg = svc.process_prompt(workspace_id=ws.name, prompt=prompt)
        assert msg.content.startswith("Invio questa mail a **Mario Rossi**") and "10 secondi" in msg.content and "non si può ritirare" in msg.content
        msg.metadata["_prompt"] = prompt
        done = _accept(svc, ws, msg)
        assert "parte tra 10 secondi" in done.content and fake.sent == [] and len(fake.drafts) == 1
        undo_mod.undo(ws, done.metadata["undo_execution_id"])
        time.sleep(0.1)
        assert fake.sent == [] and len(fake.drafts) == 1, "cancelled in time: never sent, kept as a draft"

        # without Undo it leaves after the window
        monkeypatch.setattr(mail_send, "SEND_DELAY_SECONDS", 0.05)
        svc._router_provider_override = Model({"action": "mail_reply", "mail_query": "from:rossi", "instructions": "arriva lunedì", "send": "true"},
                                              {"subject": "x", "body": "Ciao Mario,\n\narriva lunedì."})
        msg2 = svc.process_prompt(workspace_id=ws.name, prompt=prompt, session_id=msg.session_id)
        msg2.metadata["_prompt"] = prompt
        done2 = _accept(svc, ws, msg2)
        for _ in range(40):
            if fake.sent:
                break
            time.sleep(0.05)
        assert len(fake.sent) == 1
        assert undo_mod.describe(ws, ws.action_store.get_execution(done2.metadata["undo_execution_id"]))["reason"] == "already_sent"
    finally:
        ws.close()


def test_send_needs_the_word_send_and_inviala_sends_the_draft_just_made(tmp_path, monkeypatch):
    from aether.actions import mail_send

    ws = Workspace.init(tmp_path, name="gmail-send-draft")
    try:
        fake = SendingGmail()
        svc = _wire(ws, monkeypatch, fake)
        monkeypatch.setattr(mail_send, "SEND_DELAY_SECONDS", 5.0)
        # the model says send, but the user never said "invia": only a draft
        svc._router_provider_override = Model({"action": "mail_reply", "mail_query": "from:rossi", "instructions": "ok", "send": "true"},
                                              {"subject": "x", "body": "Va bene."})
        prompt = "rispondi a Rossi che va bene"
        msg = svc.process_prompt(workspace_id=ws.name, prompt=prompt)
        assert msg.metadata["resolved_action"]["action_id"] == "gmail.create_draft"
        msg.metadata["_prompt"] = prompt
        _accept(svc, ws, msg)
        (draft_id,) = fake.drafts
        svc._router_provider_override = Model({"action": "mail_send_draft"})
        send = svc.process_prompt(workspace_id=ws.name, prompt="ok inviala", session_id=msg.session_id)
        assert send.metadata["resolved_action"]["action_id"] == "gmail.send" and send.metadata["resolved_action"]["args"]["draft_id"] == draft_id
        assert "Invio questa mail a **Mario Rossi**" in send.content
        mail_send.cancel(draft_id)
    finally:
        ws.close()


class FakeGitHub:
    def __init__(self):
        self.created, self.updated = [], []

    def execute(self, op, params):
        if op == "github.list_repos":
            data = {"repositories": [{"full_name": "lom3e/aether", "name": "aether", "private": True, "description": "Assistente", "updated_at": "2026-10-22T10:00:00Z"},
                                     {"full_name": "lom3e/sito", "name": "sito", "private": False, "description": "", "updated_at": "2026-10-01T10:00:00Z"}]}
        elif op == "github.list_issues":
            data = {"issues": [{"number": 3, "title": "Bug orb", "html_url": "https://github.com/lom3e/aether/issues/3", "user": {"login": "lom3e"}},
                               {"number": 4, "title": "una PR", "pull_request": {}, "user": {"login": "x"}}]}
        elif op == "github.create_issue":
            self.created.append(params)
            data = {"number": 7, "title": params["title"], "html_url": "https://github.com/lom3e/aether/issues/7"}
        elif op == "github.update_issue":
            self.updated.append(params)
            data = {"number": params["issue_number"], "state": params["state"]}
        else:
            data = {}
        return SimpleNamespace(success=True, data=data, error="")


def test_github_from_chat_lists_for_real_and_opens_an_issue_only_after_confirmation(tmp_path, monkeypatch):
    from aether.connections.models import ConnectionStatus

    ws = Workspace.init(tmp_path, name="github-chat")
    try:
        gh = FakeGitHub()
        svc = ws.personal
        monkeypatch.setattr(ws.connections, "get_connection", lambda ws_id, prov: SimpleNamespace(status=ConnectionStatus.VERIFIED, auth_metadata={"token": "t"}, last_verification_error=""))
        monkeypatch.setattr(ws.connections, "get_github_connector", lambda ws_id: gh)
        svc._router_provider_override = Model({"action": "github_repos"})
        repos = svc.process_prompt(workspace_id=ws.name, prompt="elencami i repository")
        assert "**lom3e/aether** 🔒 — Assistente" in repos.content and "**lom3e/sito**" in repos.content and "Vuoi che" not in repos.content
        svc._router_provider_override = Model({"action": "github_issues", "repo": "aether"})
        issues = svc.process_prompt(workspace_id=ws.name, prompt="che issue ci sono su aether?", session_id=repos.session_id)
        assert "#3" in issues.content and "Bug orb" in issues.content and "una PR" not in issues.content
        svc._router_provider_override = Model({"action": "github_create_issue", "repo": "aether", "issue_title": "Orb con riquadro", "issue_body": "Dietro la sfera resta un riquadro chiaro."})
        prompt = "apri una issue su aether: orb con riquadro"
        card = svc.process_prompt(workspace_id=ws.name, prompt=prompt)
        assert "Apro questa issue in **lom3e/aether**" in card.content and gh.created == []
        card.metadata["_prompt"] = prompt
        done = _accept(svc, ws, card)
        assert gh.created and done.content.startswith("Fatto: ho aperto la issue #7 **Orb con riquadro** in lom3e/aether")
        undo_mod.undo(ws, done.metadata["undo_execution_id"])
        assert gh.updated == [{"full_name": "lom3e/aether", "owner": None, "repository": None, "issue_number": 7, "state": "closed"}]
        svc._router_provider_override = Model({"action": "github_issues", "repo": "inesistente"})
        assert "Non trovo il repository" in svc.process_prompt(workspace_id=ws.name, prompt="issue di inesistente").content
    finally:
        ws.close()


def test_the_model_is_told_exactly_what_aether_can_do():
    import aether.core.context as ctx

    text = open(ctx.__file__, encoding="utf-8").read()
    assert "GitHub (list repositories, open issues and pull requests, open an issue)" in text
    assert "Never claim other abilities on these services." in text
