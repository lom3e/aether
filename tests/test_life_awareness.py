"""Aether keeps an eye on your life without being asked twice: money owed (and a kind reminder after a week), clients you have
not heard from, the week on Friday evening, what you missed while away, what to know ten minutes before a meeting, and the
same close of the day from Telegram."""
from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

from aether.life import catchup, meeting_prep, presence_brief
from aether.life.store import LifeStore, life_store_for
from aether.workspace.workspace import Workspace

DAY = 86400


class Model:
    def __init__(self, payload):
        self.payload = payload

    def generate(self, messages):
        return SimpleNamespace(content=json.dumps(self.payload))


class Gmail:
    def __init__(self, mails):
        self.mails, self.queries = mails, []

    def search(self, query="", limit=10):
        self.queries.append(query)
        return self.mails[:limit]


def test_money_from_a_sentence_is_confirmed_saved_undone_and_shown_to_the_model(tmp_path):
    ws = Workspace.init(tmp_path, name="money")
    try:
        svc = ws.personal
        store = life_store_for(ws)
        svc._router_provider_override = Model({"action": "life_note", "note_kind": "money", "contact_name": "Mario Rossi", "amount": "200",
                                               "currency": "EUR", "direction": "owed_to_me", "title": "il sito"})
        card = svc.process_prompt(workspace_id=ws.name, prompt="Mario Rossi mi deve 200 euro per il sito")
        assert card.metadata["status"] == "proposal_pending"
        assert "Segno che **Mario Rossi** ti deve **200 €** per il sito" in card.content
        done = svc.process_prompt(workspace_id=ws.name, prompt="sì", session_id=card.session_id)
        [m] = store.list_money()
        assert (m["direction"], m["amount"], m["what"]) == ("owed_to_me", 200.0, "il sito")
        from aether.life.context import user_context

        assert "- Mario Rossi owes the user 200 € for il sito" in user_context(ws)
        svc.process_prompt(workspace_id=ws.name, prompt="annulla", session_id=card.session_id)
        assert store.list_money() == [] and done.metadata.get("undo_execution_id")
    finally:
        ws.close()


def test_after_a_week_the_brief_offers_a_kind_reminder_once(tmp_path):
    store = LifeStore(tmp_path / "life.db")
    c = store.add_contact("Mario Rossi", kind="client")
    m = store.add_money(c["id"], "owed_to_me", 200, what="il sito")
    import sqlite3

    with sqlite3.connect(store.path) as db:  # it was noted nine days ago
        db.execute("UPDATE money SET created_at=created_at-? WHERE id=?", (9 * DAY, m["id"]))
    now = dt.datetime.now().astimezone()
    out = presence_brief.build(None, store, now=now, events=[], gmail_connected=False, with_weather=False)
    assert "Mario Rossi ti deve 200 € da 9 giorni. Vuoi che prepari un sollecito gentile?" in out["text"]
    assert out["offer"]["type"] == "money_nudge"
    res = presence_brief.accept(None, store, out["offer"])
    assert res["prompt"] == "Scrivi a Mario Rossi un sollecito breve e gentile per i 200 € di il sito che mi deve."
    again = presence_brief.build(None, store, now=now, events=[], gmail_connected=False, with_weather=False)
    assert (again["offer"] or {}).get("type") != "money_nudge", "asked once a week at most"
    young = store.add_money(c["id"], "owed_to_me", 50)
    assert presence_brief._money_offer(store, dt.datetime.fromtimestamp(young["created_at"] + DAY).astimezone(), False) is None


def test_a_client_not_heard_from_in_three_weeks_gets_two_warm_lines_offered(tmp_path):
    store = LifeStore(tmp_path / "life.db")
    c = store.add_contact("Laura Bianchi", kind="client")
    store.add_job("Sito vetrina", contact_id=c["id"])
    store.add_contact("Gianni", kind="client")  # never worked with: no nudge
    now = dt.datetime.now().astimezone() + dt.timedelta(days=24)
    text, offer = presence_brief._reconnect_offer(store, now, False)
    assert text == "Non senti Laura da 3 settimane. Le scrivo due righe per sentire come va?"
    assert offer["type"] == "reconnect" and "Laura Bianchi" in offer["prompt"]
    presence_brief.decline(store, offer)
    assert presence_brief._reconnect_offer(store, now, False) is None, "not again for a month"
    from aether.life.person_reminders import touch_mentioned

    store2 = LifeStore(tmp_path / "life2.db")
    c2 = store2.add_contact("Laura Bianchi", kind="client")
    store2.add_job("Sito", contact_id=c2["id"])
    touch_mentioned(store2, "domani chiamo Laura")
    assert presence_brief._reconnect_offer(store2, dt.datetime.now().astimezone() + dt.timedelta(days=5), False) is None


def test_friday_evening_adds_the_week(tmp_path):
    store = LifeStore(tmp_path / "life.db")
    fri = dt.datetime(2026, 10, 30, 19, 0).astimezone()
    j = store.add_job("Preventivo Rossi", due_at=(fri - dt.timedelta(days=2)).timestamp())
    store.update_job(j["id"], status="done")
    store.add_job("Consegna sito", due_at=dt.datetime(2026, 11, 3, 9, 0).astimezone().timestamp())
    out = presence_brief.evening(None, store, now=fri)
    assert "Questa settimana hai chiuso 1 cosa." in out["text"]
    assert "La settimana prossima: martedì «Consegna sito»." in out["text"]


def test_what_you_missed_while_away(tmp_path):
    store = LifeStore(tmp_path / "life.db")
    now = dt.datetime(2026, 10, 27, 15, 0).astimezone()
    left = now - dt.timedelta(hours=5)
    catchup.mark_seen(store, left.timestamp())
    assert catchup.mark_seen(store, now.timestamp()) >= 4.9 and store.settings()["back_from"] == left.timestamp()
    store.add_job("Chiamare il commercialista", due_at=(now - dt.timedelta(hours=1)).timestamp())
    gmail = Gmail([{"from": "Mario Rossi <mario@x.it>", "subject": "Preventivo"}, {"from": "Laura <l@x.it>", "subject": "Contratto"}])
    events = [{"title": "Call con Mario", "start": (now + dt.timedelta(hours=1)).timestamp()}]
    timeline = [{"created_at": (now - dt.timedelta(hours=2)).isoformat(), "undone": False}]
    out = catchup.build(None, store, now=now, gmail=gmail, events=events, timeline=timeline)
    assert out["text"] == ("Mentre eri via: è scaduto «Chiamare il commercialista». 2 mail nuove, da Mario Rossi, Laura. "
                           "Ho cambiato 1 cosa per te: le trovi in Riavvolgi. Il prossimo impegno: Call con Mario alle 16:00.")
    assert "newer_than:6h" in gmail.queries[0] and "-category:promotions" in gmail.queries[0]
    quiet = catchup.build(None, LifeStore(tmp_path / "q.db"), now=now, since=left.timestamp())
    assert quiet["changes"] == 0 and quiet["text"] == "Mentre eri via non è successo niente di nuovo."


def test_ten_minutes_before_a_meeting_with_someone_known(tmp_path):
    store = LifeStore(tmp_path / "life.db")
    c = store.add_contact("Mario Rossi", kind="client", email="mario@rossi.it")
    store.add_job("Mandare il preventivo", contact_id=c["id"])
    store.add_money(c["id"], "owed_to_me", 200, what="sito")
    store.add_reminder("Chiedergli la fattura", contact_id=c["id"], source="person")
    now = dt.datetime(2026, 10, 27, 14, 50).astimezone()
    ev = {"id": "ev1", "title": "Allineamento", "start_time": (now + dt.timedelta(minutes=10)).isoformat(),
          "attendees": [{"email": "mario@rossi.it", "name": "Mario"}]}
    gmail = Gmail([{"subject": "Re: preventivo"}])
    text = meeting_prep.brief_for(store, ev, gmail=gmail)
    assert text == ("Per Mario Rossi hai aperto: «Mandare il preventivo». Mario Rossi ti deve 200 € (sito). "
                    "Volevi ricordarti: «Chiedergli la fattura». Ultima mail: «Re: preventivo».")
    sent = []
    ws = SimpleNamespace(id="w", notifications=SimpleNamespace(notify=lambda *a, **k: sent.append(a)))
    assert meeting_prep.tick(ws, store, now=now, events=[ev], gmail=gmail) == [f"ev1@{int((now + dt.timedelta(minutes=10)).timestamp())}"]
    assert sent[0][2] == "Tra 10 minuti: Allineamento" and "Mandare il preventivo" in sent[0][3]
    assert meeting_prep.tick(ws, store, now=now + dt.timedelta(minutes=1), events=[ev], gmail=gmail) == [], "once per meeting"
    stranger = {"id": "ev2", "title": "Dentista", "start_time": (now + dt.timedelta(minutes=10)).isoformat()}
    assert meeting_prep.tick(ws, store, now=now, events=[stranger]) == [] and len(sent) == 1, "nothing to say: no notification"


def test_telegram_closes_the_day_and_the_yes_button_moves_what_is_left(tmp_path, monkeypatch):
    from aether.connections import telegram_mobile as tm

    ws = Workspace.init(tmp_path, name="tg-evening")
    try:
        store = life_store_for(ws)
        now = dt.datetime.now().astimezone()
        j = store.add_job("Mandare il preventivo", due_at=(now - dt.timedelta(hours=1)).timestamp())
        sent = []
        tg = SimpleNamespace(send_message=lambda **k: sent.append(k), answer_callback_query=lambda *a, **k: None)
        bot = tm.TelegramMobile(ws)
        out = bot._brief(tg, 1, "it", evening=True)
        assert out["status"] == "brief_with_offer" and "La sposto a domani?" in sent[-1]["text"]
        data = sent[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        assert data == "by:roll_over:@" and len(data.encode()) <= 64
        monkeypatch.setattr(bot, "_allowed", lambda: ["1"])
        bot._callback(tg, {"id": "q", "data": data, "message": {"chat": {"id": 1}}})
        assert store.get_job(j["id"])["due_at"] > now.timestamp(), "moved to tomorrow"
        assert sent[-1]["text"] == "Fatto: spostate a domani. Buona serata."
        bot._callback(tg, {"id": "q2", "data": data, "message": {"chat": {"id": 1}}})
        assert sent[-1]["text"] == "Questa proposta non è più valida.", "a button works once"
    finally:
        ws.close()


def test_money_sentences_are_understood_without_the_model_even_when_it_is_down():
    from aether.personal import tool_router

    class Down:
        def generate(self, messages):
            raise TimeoutError("read timed out")

    r = tool_router.route("Mario mi deve 200 euro per il sito", provider=Down())
    assert (r["kind"], r["contact_name"], r["amount"], r["direction"], r["title"]) == ("money", "Mario", 200.0, "owed_to_me", "il sito")
    wrong = Model({"action": "life_note", "note_kind": "reminder", "title": "200 euro per il sito", "contact_name": "Mario"})
    assert tool_router.route("Mario mi deve 200 euro per il sito", provider=wrong)["kind"] == "money", "the sentence wins over a wrong guess"
    assert tool_router.route("Mario Rossi mi deve ancora 1.500,50 euro", provider=Down())["amount"] == 1500.5
    assert tool_router.route("devo 35 € a Laura per la cena", provider=Down())["direction"] == "i_owe"
    assert tool_router.route("Ann owes me $80", provider=Down())["currency"] == "USD"
    assert tool_router.route("che tempo fa?", provider=Down())["action"] == "none"


def test_a_meeting_is_prepared_once_the_person_is_saved_even_if_the_first_check_found_nobody(tmp_path):
    store = LifeStore(tmp_path / "life.db")
    now = dt.datetime(2026, 10, 27, 10, 0).astimezone()
    ev = {"id": "ev9", "title": "Call con Mario", "start_time": (now + dt.timedelta(minutes=10)).isoformat()}
    sent = []
    ws = SimpleNamespace(id="w", notifications=SimpleNamespace(notify=lambda *a, **k: sent.append(a)))
    assert meeting_prep.tick(ws, store, now=now, events=[ev]) == []
    c = store.add_contact("Mario", kind="client")
    store.add_job("Mandare il preventivo", contact_id=c["id"])
    assert len(meeting_prep.tick(ws, store, now=now + dt.timedelta(minutes=1), events=[ev])) == 1
    moved = {**ev, "start_time": (now + dt.timedelta(minutes=70)).isoformat()}
    assert len(meeting_prep.tick(ws, store, now=now + dt.timedelta(minutes=61), events=[moved])) == 1, "moved: prepared again"


def test_a_slow_network_is_explained_in_plain_words():
    from aether.personal.service import format_mail_response

    text = format_mail_response(None, "in:inbox", "Failed to reach Google token endpoint during refresh: The read operation timed out")
    assert text.startswith("Google non risponde in questo momento") and "token" not in text
