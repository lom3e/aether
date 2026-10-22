"""Gmail, read-only: listing is done on this computer; the request is routed by the model only when Gmail is connected."""
from __future__ import annotations

import base64
import json
from types import SimpleNamespace

from aether.actions.models import ActionExecutionStatus
from aether.connections.gmail import GMAIL_SCOPES, GmailConnector, _text_from_payload
from aether.connections.oauth import OAUTH_SPECS
from aether.personal.service import format_mail_response
from aether.workspace.workspace import Workspace


def test_only_the_read_only_scope_is_requested_and_the_calendar_client_is_reused():
    assert "https://www.googleapis.com/auth/gmail.readonly" in OAUTH_SPECS["gmail"]["scopes"]
    assert not [s for s in OAUTH_SPECS["gmail"]["scopes"] if "gmail" in s and not s.endswith("readonly")]
    assert OAUTH_SPECS["gmail"]["client_from"] == "google_calendar"
    assert GMAIL_SCOPES[-1].endswith("gmail.readonly")


def test_search_returns_sender_subject_and_unread(monkeypatch):
    c = GmailConnector(auth_metadata={"access_token": "t"})
    calls = []

    def api(endpoint, method="GET", params=None, data=None, retry_on_401=True):
        calls.append(endpoint)
        if endpoint == "users/me/messages":
            return {"messages": [{"id": "m1"}]}
        return {"id": "m1", "threadId": "t1", "internalDate": "1792569600000", "snippet": "Ciao, ti mando il preventivo &amp; il resto", "labelIds": ["UNREAD", "INBOX"],
                "payload": {"headers": [{"name": "From", "value": '"Mario Rossi" <mario@example.com>'}, {"name": "Subject", "value": "Preventivo"}]}}

    monkeypatch.setattr(c, "_api_request", api)
    msgs = c.search("is:unread", 5)
    assert msgs[0]["from"] == "Mario Rossi" and msgs[0]["subject"] == "Preventivo" and msgs[0]["unread"] is True
    assert msgs[0]["snippet"] == "Ciao, ti mando il preventivo & il resto"
    assert calls == ["users/me/messages", "users/me/messages/m1"]


def test_text_is_extracted_from_plain_or_html_parts():
    enc = lambda t: base64.urlsafe_b64encode(t.encode()).decode()
    assert _text_from_payload({"mimeType": "multipart/alternative", "parts": [{"mimeType": "text/plain", "body": {"data": enc("Ciao Matteo")}}]}) == "Ciao Matteo"
    html_only = {"mimeType": "text/html", "body": {"data": enc("<style>p{}</style><p>Fattura <b>n. 3</b></p>")}}
    assert _text_from_payload(html_only) == "Fattura n. 3"


def test_the_listing_is_plain_and_honest():
    text = format_mail_response([{"from": "Mario Rossi", "subject": "Preventivo", "internal_ts": 1792569600, "unread": True, "snippet": "Ciao"}], "is:unread")
    assert "● **Mario Rossi** — Preventivo" in text and "is:unread" in text
    assert format_mail_response([], "from:enel").startswith("Nessuna mail trovata")
    assert "Collegamenti" in format_mail_response(None, "", error="401")


class Model:
    def __init__(self, payload):
        self.payload = payload

    def generate(self, messages):
        return SimpleNamespace(content=json.dumps(self.payload))


def test_mail_questions_are_answered_from_gmail_when_connected(tmp_path, monkeypatch):
    ws = Workspace.init(tmp_path, name="gmail")
    try:
        svc = ws.personal
        svc._router_provider_override = Model({"action": "mail_search", "mail_query": "from:rossi"})
        msg = svc.process_prompt(workspace_id=ws.name, prompt="mi ha scritto Rossi?")
        assert "collega Gmail" in msg.content and "solo lettura" in msg.content, "not connected: say so"
        monkeypatch.setattr(svc, "_provider_ready", lambda ws_id, prov: True)
        real = svc.action_executor.execute
        seen = []

        def execute(*a, **k):
            if k.get("action_id") == "gmail.search":
                seen.append(k["input_data"])
                return SimpleNamespace(status=ActionExecutionStatus.SUCCEEDED, output_data={"messages": [{"from": "Mario Rossi", "subject": "Preventivo", "unread": False}]}, error_message="")
            return real(*a, **k)

        monkeypatch.setattr(svc.action_executor, "execute", execute)
        msg = svc.process_prompt(workspace_id=ws.name, prompt="mi ha scritto Rossi?")
        assert seen == [{"query": "from:rossi", "limit": 10}]
        assert "**Mario Rossi** — Preventivo" in msg.content
    finally:
        ws.close()
