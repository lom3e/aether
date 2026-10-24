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
    def __init__(self, items):
        self.items = items
        self.seen = ""

    def generate(self, messages):
        self.seen = messages[-1].content
        return SimpleNamespace(content=json.dumps({"items": self.items}))


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
