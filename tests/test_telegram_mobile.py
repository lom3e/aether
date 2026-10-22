"""Aether on the phone through Telegram: private until paired, one conversation per chat, changes confirmed with buttons."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from aether.connections import telegram_mobile as tm
from aether.workspace.workspace import Workspace


class FakeTG:
    def __init__(self):
        self.sent = []
        self.answers = []

    def send_message(self, chat_id=None, text="", reply_markup=None, parse_mode="Markdown", **kw):
        self.sent.append({"chat": chat_id, "text": text, "markup": reply_markup, "parse_mode": parse_mode})
        return {}

    def answer_callback_query(self, cb_id, text="", show_alert=False):
        self.answers.append(text)

    def get_updates(self, offset=None, timeout=10):
        return []


@pytest.fixture
def mobile(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHER_DISABLE_TELEGRAM_POLLING", "1")
    ws = Workspace.init(tmp_path, name="tg")
    monkeypatch.setattr("aether.connections.telegram.TelegramConnector.verify", lambda self, auth_metadata=None, live_check=False: (True, "Telegram Bot @aether_test_bot verified successfully."))
    m = tm.TelegramMobile(ws)
    fake = FakeTG()
    monkeypatch.setattr(m, "_connector", lambda: fake)
    monkeypatch.setattr(m, "start", lambda: True)
    m.fake = fake
    yield m
    ws.close()


def _msg(chat, text, name="Matteo"):
    return {"update_id": 1, "message": {"chat": {"id": chat}, "from": {"first_name": name}, "text": text}}


def test_setup_gives_a_one_time_link_and_strangers_are_refused(mobile, monkeypatch):
    calls = []
    monkeypatch.setattr(mobile.ws.personal, "process_prompt", lambda **k: calls.append(k))
    res = mobile.setup("123456789:" + "A" * 35)
    assert res["status"] == "ok" and res["link"].startswith("https://t.me/aether_test_bot?start=")
    assert mobile.handle(_msg(42, "che impegni ho?"))["status"] == "unauthorized"
    assert mobile.handle(_msg(42, "/start wrongcode"))["status"] == "unauthorized"
    assert calls == [], "an unpaired chat never reaches the assistant"
    assert mobile.handle(_msg(42, "/start " + res["code"]))["status"] == "paired"
    assert mobile.status()["paired"] == [{"chat_id": "42", "name": "Matteo"}]
    assert mobile.handle(_msg(77, "/start " + res["code"]))["status"] == "unauthorized", "a link pairs one chat only"


def test_a_paired_chat_keeps_one_conversation(mobile, monkeypatch):
    code = mobile.setup("123456789:" + "A" * 35)["code"]
    mobile.handle(_msg(42, "/start " + code))
    seen = []

    def fake_prompt(**k):
        seen.append(k.get("session_id"))
        return SimpleNamespace(session_id="sess-1", content="**Ecco** i tuoi impegni", metadata={}, steps=[], action_execution_id=None)

    monkeypatch.setattr(mobile.ws.personal, "process_prompt", fake_prompt)
    mobile.handle(_msg(42, "che impegni ho domani?"))
    mobile.handle(_msg(42, "cancellali"))
    assert seen == [None, "sess-1"], "the follow-up continues the same conversation"
    assert mobile.fake.sent[-1]["text"] == "Ecco i tuoi impegni" and mobile.fake.sent[-1]["parse_mode"] == ""


def test_a_change_is_confirmed_with_a_button_and_then_runs_with_the_authority(mobile, monkeypatch):
    code = mobile.setup("123456789:" + "A" * 35)["code"]
    mobile.handle(_msg(42, "/start " + code))
    calls = []

    def fake_prompt(**k):
        calls.append(k)
        if k.get("authority") is None:
            return SimpleNamespace(session_id="s", content="Sto per spostare **Riunione**", metadata={"status": "proposal_pending", "proposal_id": "p1", "proposal_version": 2}, steps=[], action_execution_id=None)
        return SimpleNamespace(session_id="s", content="Fatto", metadata={}, steps=[], action_execution_id=None)

    monkeypatch.setattr(mobile.ws.personal, "process_prompt", fake_prompt)
    accepted = []
    monkeypatch.setattr(mobile.ws.personal, "accept_proposal", lambda **k: accepted.append(k) or (None, "AUTH"))
    assert mobile.handle(_msg(42, "sposta la riunione a venerdì"))["status"] == "proposal_sent"
    buttons = mobile.fake.sent[-1]["markup"]["inline_keyboard"][0]
    assert [b["callback_data"] for b in buttons] == ["ok:p1:2", "no:p1"]
    stranger = {"callback_query": {"id": "c0", "data": "ok:p1:2", "message": {"chat": {"id": 99}}}}
    assert mobile.handle(stranger)["status"] == "unauthorized" and accepted == []
    mobile.handle({"callback_query": {"id": "c1", "data": "ok:p1:2", "message": {"chat": {"id": 42}}}})
    assert accepted and accepted[0]["proposal_id"] == "p1" and accepted[0]["expected_version"] == 2
    assert calls[-1]["authority"] == "AUTH" and calls[-1]["prompt"] == "sposta la riunione a venerdì"


def test_a_done_change_offers_undo_and_undo_runs_the_inverse(mobile, monkeypatch):
    code = mobile.setup("123456789:" + "A" * 35)["code"]
    mobile.handle(_msg(42, "/start " + code))
    monkeypatch.setattr(mobile.ws.personal, "process_prompt", lambda **k: SimpleNamespace(session_id="s", content="Fatto: ho spostato **Riunione**", metadata={"undo_execution_id": "ax-1"}, steps=[], action_execution_id="ax-1"))
    assert mobile.handle(_msg(42, "sposta"))["status"] == "done_with_undo"
    assert mobile.fake.sent[-1]["markup"]["inline_keyboard"][0][0]["callback_data"] == "undo:ax-1"
    undone = []
    monkeypatch.setattr("aether.actions.undo.undo", lambda ws, ex_id: undone.append(ex_id) or {"result": "moved_back"})
    assert mobile.handle({"callback_query": {"id": "c", "data": "undo:ax-1", "message": {"chat": {"id": 42}}}})["status"] == "undone"
    assert undone == ["ax-1"] and "come prima" in mobile.fake.sent[-1]["text"]
