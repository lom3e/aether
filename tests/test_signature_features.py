"""Aether's own features: reminders tied to a person ("quando sento Mario…") that come back when the person does, the close of
the day (what got done, move what is left to tomorrow with one yes), "annulla" said right after a change, and the profile
(name and city) the welcome fills in."""
from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

from aether.life import presence_brief
from aether.life.person_reminders import for_events, surface_in_chat
from aether.life.store import LifeStore, life_store_for
from aether.workspace.workspace import Workspace


class Model:
    def __init__(self, payload):
        self.payload = payload

    def generate(self, messages):
        return SimpleNamespace(content=json.dumps(self.payload))


def test_a_reminder_tied_to_a_person_is_saved_without_a_date_and_comes_back_when_they_are_mentioned(tmp_path):
    ws = Workspace.init(tmp_path, name="person-rem")
    try:
        svc = ws.personal
        store = life_store_for(ws)
        svc._router_provider_override = Model({"action": "life_note", "note_kind": "reminder", "title": "Chiedergli la fattura",
                                               "contact_name": "Mario Rossi", "trigger": "person", "due": "2026-10-30"})
        card = svc.process_prompt(workspace_id=ws.name, prompt="quando sento Mario Rossi ricordami di chiedergli la fattura")
        assert card.metadata["status"] == "proposal_pending"
        assert "appena si parla di **Mario Rossi**" in card.content and "**Chiedergli la fattura**" in card.content
        svc.process_prompt(workspace_id=ws.name, prompt="sì", session_id=card.session_id)
        [rem] = store.list_reminders()
        assert rem["source"] == "person" and rem["due_at"] is None, "no date: it waits for the person"
        assert [c["name"] for c in store.list_contacts()] == ["Mario Rossi"] and store.list_contacts()[0]["kind"] == "person"

        note = surface_in_chat(store, "domani ho una call con Mario")
        assert note == "📌 Mi avevi chiesto di ricordartelo quando si parlava di Mario Rossi: **Chiedergli la fattura**."
        assert store.list_reminders() == [], "said once, then done"
        assert surface_in_chat(store, "domani ho una call con Mario") == ""
    finally:
        ws.close()


def test_the_brief_mentions_a_person_reminder_when_today_has_a_meeting_with_them(tmp_path):
    store = LifeStore(tmp_path / "life.db")
    c = store.add_contact("Laura Bianchi", kind="client")
    store.add_reminder("Parlarle del contratto", contact_id=c["id"], source="person")
    now = dt.datetime(2026, 10, 27, 8, 30).astimezone()
    start = dt.datetime(2026, 10, 27, 15, 0).astimezone()
    events = [{"summary": "Call con Laura", "start": {"dateTime": start.isoformat()}}]
    assert [x[1]["name"] for x in for_events(store, [{"title": "Call con Laura"}])] == ["Laura Bianchi"]
    out = presence_brief.build(None, store, now=now, events=events, gmail_connected=False, with_weather=False)
    assert "Alle 15:00 vedi Laura Bianchi: ricordati «Parlarle del contratto»." in out["text"]
    assert store.list_reminders(), "the brief only mentions it: you may not meet them after all"


def test_the_evening_closes_the_day_and_one_yes_moves_what_is_left_to_tomorrow(tmp_path):
    store = LifeStore(tmp_path / "life.db")
    store.update_settings(user_name="Matteo Rossi")
    now = dt.datetime(2026, 10, 26, 19, 0).astimezone()
    today_10 = dt.datetime(2026, 10, 26, 10, 0).astimezone().timestamp()
    late = dt.datetime(2026, 10, 24, 15, 30).astimezone().timestamp()
    j = store.add_job("Mandare il preventivo", due_at=today_10)
    r = store.add_reminder("Chiamare Laura", due_at=late)
    done = store.add_job("Fattura a Verdi", due_at=today_10)
    store.update_job(done["id"], status="done")
    store.add_reminder("Chiedere a Mario", source="person")  # no date: never rolled over

    ev = presence_brief.evening(None, store, now=now)
    assert ev["text"] == ("Buonasera, Matteo. Oggi hai chiuso 1 cosa. Restano aperte 2 cose: «Chiamare Laura», «Mandare il preventivo». "
                          "Le sposto a domani?")
    assert ev["offer"]["type"] == "roll_over"

    out = presence_brief.accept(None, store, ev["offer"], language="it")
    assert out["text"] == "Fatto: spostate a domani. Buona serata."
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    j2, r2 = store.get_job(j["id"]), store.get_reminder(r["id"])
    assert dt.datetime.fromtimestamp(j2["due_at"]).date() == tomorrow and dt.datetime.fromtimestamp(j2["due_at"]).hour == 10
    assert dt.datetime.fromtimestamp(r2["due_at"]).strftime("%H:%M") == "15:30", "the time of day is kept"

    empty = LifeStore(tmp_path / "empty.db")
    assert presence_brief.evening(None, empty, now=now)["text"] == "", "nothing done, nothing open: Aether stays quiet"


def test_saying_annulla_right_after_a_change_undoes_it(tmp_path):
    ws = Workspace.init(tmp_path, name="voice-undo")
    try:
        svc = ws.personal
        store = life_store_for(ws)
        svc._router_provider_override = Model({"action": "life_note", "note_kind": "reminder", "title": "Chiamare Laura",
                                               "due": (dt.datetime.now() + dt.timedelta(days=1)).strftime("%Y-%m-%dT10:00")})
        card = svc.process_prompt(workspace_id=ws.name, prompt="ricordami domani alle 10 di chiamare Laura")
        done = svc.process_prompt(workspace_id=ws.name, prompt="sì", session_id=card.session_id)
        assert done.metadata.get("undo_execution_id") and len(store.list_reminders()) == 1
        undone = svc.process_prompt(workspace_id=ws.name, prompt="annulla", session_id=card.session_id)
        assert undone.content == "Annullato: è tutto come prima." and undone.metadata["status"] == "undone"
        assert store.list_reminders() == []
    finally:
        ws.close()


def test_the_profile_name_greets_and_signs(tmp_path):
    ws = Workspace.init(tmp_path, name="profile")
    try:
        from aether.life.context import user_context

        store = life_store_for(ws)
        store.update_settings(user_name="Matteo Rossi")
        assert "The user's name: Matteo Rossi (sign the user's mails with it; never sign as Aether)." in user_context(ws)
        out = presence_brief.build(ws, store, now=dt.datetime(2026, 10, 27, 8, 0).astimezone(), events=[], gmail_connected=False, with_weather=False)
        assert out["text"].startswith("Buongiorno, Matteo.")
    finally:
        ws.close()


def test_the_router_ties_a_reminder_to_the_person_even_when_the_model_forgets_and_never_notes_a_question():
    from aether.personal import tool_router

    now = dt.datetime(2026, 10, 26, 21, 0).astimezone()
    r = tool_router.route("quando sento Mario Rossi ricordami di chiedergli la fattura", now=now,
                          provider=Model({"action": "life_note", "note_kind": "reminder", "title": "Chiedergli la fattura", "due": "2026-10-27"}))
    assert (r["trigger"], r["contact_name"], r["due_at"]) == ("person", "Mario Rossi", None)
    q = tool_router.route("domani ho una call con Mario, cosa gli devo dire?", now=now,
                          provider=Model({"action": "life_note", "note_kind": "reminder", "title": "x", "due": "2026-10-27"}))
    assert q["action"] == "none"
    ask = tool_router.route("mi ricordi domani di chiamare Laura?", now=now,
                            provider=Model({"action": "life_note", "note_kind": "reminder", "title": "Chiamare Laura", "due": "2026-10-27T09:00"}))
    assert ask["action"] == "life_note", "a request phrased as a question is still a request"


def test_a_person_reminder_is_understood_even_when_the_model_says_none():
    from aether.personal import tool_router

    r = tool_router.route("la prossima volta che vedo Giulia ricordami di chiederle del contratto", provider=Model({"action": "none"}))
    assert (r["action"], r["kind"], r["contact_name"], r["title"], r["trigger"]) == ("life_note", "reminder", "Giulia", "Chiederle del contratto", "person")
    r3 = tool_router.route("Quando sento Giulia ricordami di chiederle del contratto", provider=Model(
        {"action": "life_note", "note_kind": "reminder", "title": "Chiederle del contratto", "contact_name": "Giulia"}))
    assert (r3["trigger"], r3["contact_name"]) == ("person", "Giulia"), "a capital Q is the same sentence"
    r2 = tool_router.route("ricordami di chiedere la fattura quando sento Mario", provider=Model({"action": "none"}))
    assert (r2["contact_name"], r2["title"]) == ("Mario", "Chiedere la fattura")


def test_a_key_repeated_empty_by_the_model_does_not_erase_its_value():
    from aether.personal import tool_router

    class Raw:
        def generate(self, messages):
            return SimpleNamespace(content='{"action":"life_note","note_kind":"reminder","contact_name":"Marco","trigger":"person",'
                                           '"title":"Ridargli il libro","due":"","title":"","due":""}')

    r = tool_router.route("appena vedo marco ricordami di ridargli il libro", provider=Raw())
    assert (r["title"], r["contact_name"], r["trigger"]) == ("Ridargli il libro", "Marco", "person")
