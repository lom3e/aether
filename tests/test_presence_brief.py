"""What the orb says when Aether opens: facts only, at most one question, in priority order; yes runs it, no stops asking."""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from aether.life import presence_brief
from aether.life.store import LifeStore

NOW = dt.datetime(2026, 10, 27, 9, 0).astimezone()  # a Tuesday morning


def _ws():
    return SimpleNamespace(id="w", conversations_db_path="", memory=None)


def _brief(store, **kw):
    return presence_brief.build(None, store, language=kw.pop("language", "it"), now=NOW, events=kw.pop("events", []), gmail_connected=kw.pop("gmail", True))


def test_quiet_day_says_hello_and_offers_the_daily_check_once(tmp_path):
    store = LifeStore(tmp_path / "l.db")
    b = _brief(store)
    assert b["text"].startswith("Buongiorno.") and b["offer"] == {"type": "watch_on"}
    presence_brief.decline(store, b["offer"])
    b = _brief(store)
    assert b["offer"] is None and b["text"] == "Buongiorno. Oggi niente di urgente."
    assert _brief(store, gmail=False)["offer"] is None


def test_next_event_overdue_and_the_promise_due_soon(tmp_path):
    store = LifeStore(tmp_path / "l.db")
    store.add_job("Fattura Bianchi", due_at=(NOW - dt.timedelta(days=2)).timestamp())
    p = store.add_promise("i_promised", "Inviare il preventivo", who="Mario Rossi", due_at=(NOW + dt.timedelta(days=3)).replace(hour=9).timestamp(),
                          message_id="s1", subject="Re: sito")
    ev = [{"title": "Lezione di Analisi", "start": (NOW + dt.timedelta(hours=1)).isoformat(), "end": (NOW + dt.timedelta(hours=2)).isoformat()}]
    b = _brief(store, events=ev)
    assert "Alle 10:00 hai Lezione di Analisi." in b["text"] and "«Fattura Bianchi» è in ritardo." in b["text"]
    assert b["offer"]["type"] == "track", "due in three days: not yet urgent, it is proposed as a job"
    store.set_promise_status(p["id"], "tracked")
    store.update_settings(promise_watch_offered=True)
    assert _brief(store, events=ev)["offer"] is None
    soon = store.add_promise("i_promised", "Mandare le foto", who="Laura", due_at=(NOW + dt.timedelta(days=1)).timestamp(), message_id="s2", subject="Foto")
    b = _brief(store, events=ev)
    assert b["offer"]["type"] == "ask" and b["offer"]["promise_id"] == soon["id"]
    assert "Hai promesso a Laura: «Mandare le foto», entro domani. Vuoi che ti prepari la mail?" in b["text"]
    assert "Laura" in b["offer"]["prompt"] and "«Foto»" in b["offer"]["prompt"]


def test_fulfilled_comes_first_and_yes_closes_the_job(tmp_path):
    store = LifeStore(tmp_path / "l.db")
    job = store.add_job("Inviare il preventivo a Rossi")
    store.add_promise("they_promised", "Mandare la fattura", who="Bianchi", due_at=(NOW - dt.timedelta(days=1)).timestamp(), message_id="r1")
    store.add_promise("fulfilled", job["title"], job_id=job["id"], message_id="s9")
    b = _brief(store)
    assert b["offer"]["type"] == "job_done" and "Lo segno come fatto?" in b["text"]
    out = presence_brief.accept(_ws(), store, b["offer"])
    assert store.get_job(job["id"])["status"] == "done" and "Segnato come fatto" in out["text"]
    b = _brief(store)
    assert b["offer"]["type"] == "ask" and "sollecito" in b["text"] and "ieri" in b["text"]


def test_track_creates_the_contact_and_the_job_and_english_works(tmp_path):
    store = LifeStore(tmp_path / "l.db")
    store.update_settings(promise_watch_offered=True)
    p = store.add_promise("they_asked", "Send the October invoice", who="Laura Bianchi", message_id="r1")
    b = _brief(store, language="en")
    assert b["text"].startswith("Good morning.") and "Laura Bianchi asked you" in b["text"] and b["offer"]["type"] == "track"
    presence_brief.accept(_ws(), store, b["offer"], language="en")
    jobs = store.list_jobs()
    assert [(j["title"], j["contact_name"]) for j in jobs] == [("Send the October invoice", "Laura Bianchi")]
    assert store.get_promise(p["id"])["status"] == "tracked"
    with pytest.raises(ValueError):
        presence_brief.accept(_ws(), store, {"type": "job_done", "promise_id": p["id"]})


def test_first_meeting_introduces_aether_and_points_at_the_next_useful_step(tmp_path):
    no_model = presence_brief.first_meeting(None, language="it", now=NOW, gmail_connected=False, has_model=False)
    assert no_model["text"].startswith("Buongiorno. Sono Aether. Tieni premuto Spazio") and "scegli il modello" in no_model["body"]
    assert no_model["offer"] is None and no_model["first"] is True
    no_gmail = presence_brief.first_meeting(None, language="en", now=NOW, gmail_connected=False, has_model=True)
    assert no_gmail["offer"] == {"type": "open", "view": "connections"} and "Gmail" in no_gmail["body"]
    assert presence_brief.first_meeting(None, now=NOW, gmail_connected=True, has_model=True)["offer"] is None
