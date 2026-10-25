"""Promise keeper: open commitments from recent mail become proposals; nothing is invented (every item points at a real
email), nothing already tracked is proposed again, and nothing is saved by the scan itself."""
from __future__ import annotations

import json
from types import SimpleNamespace

from aether.life import promises
from aether.life.store import LifeStore


class Gmail:
    def search(self, query="", limit=10):
        if "in:sent" in query:
            return [{"id": "s1", "from_raw": "Me <me@x.it>", "subject": "Re: sito", "snippet": "Ciao Mario, ti mando il preventivo entro venerdì."}]
        return [{"id": "r1", "from_raw": "Bianchi <b@x.it>", "subject": "Fattura", "snippet": "Mi mandi la fattura di ottobre?"}]


class Model:
    def __init__(self, items, fulfilled=None):
        self.items, self.fulfilled = items, fulfilled or []
        self.seen = ""

    def generate(self, messages):
        self.seen = messages[-1].content
        return SimpleNamespace(content=json.dumps({"items": self.items, "fulfilled": self.fulfilled}))


def test_scan_proposes_real_promises_only_and_skips_what_is_tracked(tmp_path):
    store = LifeStore(tmp_path / "life.db")
    store.add_job("Inviare la fattura di ottobre a Bianchi")
    model = Model([
        {"kind": "i_promised", "who": "Mario Rossi", "what": "Inviare il preventivo", "due": "2026-10-30", "message_id": "s1"},
        {"kind": "they_asked", "who": "Bianchi", "what": "Inviare la fattura di ottobre a Bianchi", "due": "", "message_id": "r1"},
        {"kind": "they_asked", "who": "Verdi", "what": "Chiamare Verdi", "due": "", "message_id": "invented"},
    ])
    out = promises.scan(None, store, gmail=Gmail(), provider=model)
    assert out["status"] == "ok" and out["scanned"] == 2
    assert [i["title"] for i in out["items"]] == ["Inviare il preventivo"], "tracked and invented items are dropped"
    assert out["items"][0]["kind"] == "i_promised" and out["items"][0]["due_at"]
    assert "ti mando il preventivo" in model.seen and len(store.list_jobs()) == 1, "the scan saves nothing"


def test_without_a_model_nothing_happens(tmp_path):
    assert promises.scan(None, LifeStore(tmp_path / "l.db"), gmail=Gmail(), provider=None)["status"] == "unavailable"


def test_they_promised_and_fulfilled_jobs_need_a_real_sent_mail_and_a_real_open_job(tmp_path):
    store = LifeStore(tmp_path / "life.db")
    job = store.add_job("Inviare il preventivo a Rossi")
    model = Model([{"kind": "they_promised", "who": "Bianchi", "what": "Mandare la fattura di ottobre", "due": "2026-10-20", "message_id": "r1"}],
                  fulfilled=[{"job_id": job["id"], "message_id": "s1"}, {"job_id": "jb-invented", "message_id": "s1"},
                             {"job_id": job["id"], "message_id": "r1"}])
    out = promises.scan(None, store, gmail=Gmail(), provider=model)
    assert [i["kind"] for i in out["items"]] == ["they_promised"]
    assert [(f["job_id"], f["message_id"]) for f in out["fulfilled"]] == [(job["id"], "s1")], "only a sent mail can close a real job"
    assert "OPEN JOBS" in model.seen and job["id"] in model.seen
    assert store.get_job(job["id"])["status"] == "open", "the scan marks nothing done"


def test_remember_keeps_proposals_once_even_after_a_no(tmp_path):
    store = LifeStore(tmp_path / "life.db")
    model = Model([{"kind": "i_promised", "who": "Mario Rossi", "what": "Inviare il preventivo", "due": "2026-10-30", "message_id": "s1"}])
    first = promises.scan(None, store, gmail=Gmail(), provider=model)
    added = promises.remember(store, first)
    assert len(added) == 1 and first["items"][0]["id"] == added[0]["id"]
    store.set_promise_status(added[0]["id"], "ignored")
    again = promises.scan(None, store, gmail=Gmail(), provider=model)
    assert promises.remember(store, again) == [] and again["items"][0]["status"] == "ignored"


def test_daily_watch_runs_only_when_turned_on_and_at_most_every_six_hours(tmp_path):
    store = LifeStore(tmp_path / "life.db")
    notes = []
    ws = SimpleNamespace(id="w", connections=SimpleNamespace(get_gmail_connector=lambda _id: Gmail()),
                         notifications=SimpleNamespace(notify=lambda *a, **k: notes.append(a)))
    model = Model([{"kind": "they_asked", "who": "Bianchi", "what": "Mandare la fattura", "due": "", "message_id": "r1"}])
    import aether.providers.resolution as res

    orig = res.resolve_provider
    res.resolve_provider = lambda **k: model
    try:
        assert promises.watch_tick(ws, store, now=1_000_000) is None, "off by default"
        store.update_settings(promise_watch=True)
        assert promises.watch_tick(ws, store, now=1_000_000) == {"added": 1, "status": "ok"}
        assert len(notes) == 1
        assert promises.watch_tick(ws, store, now=1_000_000 + 3600) is None, "not again within six hours"
        assert promises.watch_tick(ws, store, now=1_000_000 + 7 * 3600) == {"added": 0, "status": "ok"}
        assert len(notes) == 1, "nothing new, no notification"
    finally:
        res.resolve_provider = orig
