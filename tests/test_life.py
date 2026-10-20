"""People & clients, jobs, reminders, Today and sentence capture. Calendar and the model are fakes/mocks; the store, the memory
mirror, the routes and the Today logic are the real ones."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import time
from pathlib import Path

import pytest
from fastapi import HTTPException, Request

from aether.life import capture, service as life
from aether.life.store import LifeStore
from aether.providers.mock import MockProvider
from aether.providers.types import ProviderConfig
from aether.server import routes
from aether.server.app import app
from aether.workspace.workspace import Workspace

NOW = dt.datetime(2026, 10, 21, 9, 30).astimezone()  # a Wednesday


@pytest.fixture
def ws(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path / "data"))
    w = Workspace.init(tmp_path / "ws", name="Life")
    app.state.workspace = w
    yield w
    w.close()


def _req(method="GET", path="/api/life/today") -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": [], "app": app})


def _ts(days: int, hour: int = 12) -> float:
    base = NOW.replace(hour=hour, minute=0, second=0, microsecond=0) + dt.timedelta(days=days)
    return base.timestamp()


def test_contacts_jobs_reminders_crud_and_validation(tmp_path):
    s = LifeStore(tmp_path / "life.db")
    rossi = s.add_contact("Mario Rossi", kind="client", company="Rossi SRL", email="m@rossi.it")
    assert s.find_contact("rossi")["id"] == rossi["id"] and s.find_contact("verdi") is None
    s.add_contact("Anna Rossi")
    assert s.find_contact("rossi") is None, "two matches are never guessed between"
    j = s.add_job("Preventivo sito", contact_id=rossi["id"], due_at=_ts(2))
    assert s.get_job(j["id"])["contact_name"] == "Mario Rossi"
    done = s.update_job(j["id"], status="done")
    assert done["status"] == "done" and done["done_at"]
    r = s.add_reminder("Chiamare il commercialista", due_at=_ts(0))
    assert s.complete_reminder(r["id"])["done"] is True and s.list_reminders() == []
    with pytest.raises(ValueError):
        s.add_contact("  ")
    with pytest.raises(ValueError):
        s.add_job("x", contact_id="ct-nope")
    with pytest.raises(ValueError):
        s.update_job(j["id"], status="weird")
    assert s.delete_contact(rossi["id"]) and s.get_job(j["id"])["contact_id"] is None, "jobs survive the contact"


def test_contacts_and_jobs_are_mirrored_into_memory_and_forgotten_with_them(ws):
    s = LifeStore(Path(ws.conversations_db_path).parent / "life.db")
    c = s.add_contact("Mario Rossi", kind="client", company="Rossi SRL")
    life.sync_contact(ws, s, c)
    c = s.get_contact(c["id"])
    mem = ws.memory.get_memory(c["memory_id"], workspace_id=ws.id)
    assert mem and mem.category.value == "person" and "Mario Rossi" in mem.summary
    j = s.add_job("Preventivo sito", contact_id=c["id"], due_at=_ts(2))
    life.sync_job(ws, s, s.get_job(j["id"]))
    jm = ws.memory.get_memory(s.get_job(j["id"])["memory_id"], workspace_id=ws.id)
    assert jm.category.value == "project" and "Preventivo sito" in jm.summary and "Mario Rossi" in jm.summary
    s.update_job(j["id"], status="done")
    life.sync_job(ws, s, s.get_job(j["id"]))
    assert "done" in ws.memory.get_memory(s.get_job(j["id"])["memory_id"], workspace_id=ws.id).content
    assert life.forget_job(ws, s, j["id"]) and ws.memory.get_memory(jm.id, workspace_id=ws.id) is None or ws.memory.get_memory(jm.id, workspace_id=ws.id).is_deleted
    assert life.forget_contact(ws, s, c["id"])


def test_today_groups_overdue_today_and_soon_and_the_brief_states_facts(tmp_path):
    s = LifeStore(tmp_path / "life.db")
    rossi = s.add_contact("Rossi", kind="client")
    s.add_job("Fattura marzo", contact_id=rossi["id"], due_at=_ts(-2))
    s.add_job("Preventivo", contact_id=rossi["id"], due_at=_ts(0, 17))
    s.add_job("Report trimestrale", due_at=_ts(3))
    s.add_job("Lontano", due_at=_ts(30))
    s.add_job("Senza data")
    s.add_reminder("Chiamare il commercialista", due_at=_ts(0, 18))
    events = [{"summary": "Call Bianchi", "start": {"dateTime": NOW.replace(hour=15).isoformat()}}, {"summary": "Domani", "start": {"dateTime": (NOW + dt.timedelta(days=1)).isoformat()}}]
    t = life.build_today(s, now=NOW, events=events, pending_approvals=2)
    assert [j["title"] for j in t["jobs"]["overdue"]] == ["Fattura marzo"]
    assert [j["title"] for j in t["jobs"]["today"]] == ["Preventivo"] and [j["title"] for j in t["jobs"]["upcoming"]] == ["Report trimestrale"]
    assert [j["title"] for j in t["jobs"]["undated"]] == ["Senza data"]
    assert [e["title"] for e in t["events"]] == ["Call Bianchi"], "only today's appointments"
    assert t["counts"] == {"events": 1, "overdue": 1, "today": 2, "upcoming": 1} and t["empty"] is False
    it = life.brief_text(t, "it")
    assert "1 appuntamento" in it and "Call Bianchi" in it and "1 in ritardo" in it and "Preventivo (Rossi)" in it and "2 in attesa" in it
    assert "1 appointment(s)" in life.brief_text(t, "en")
    assert life.build_today(LifeStore(tmp_path / "e.db"), now=NOW)["empty"] is True
    assert life.brief_text(life.build_today(LifeStore(tmp_path / "e.db"), now=NOW), "it") == "Niente in programma per oggi."


def test_capture_returns_a_proposal_and_never_saves(ws):
    s = LifeStore(Path(ws.conversations_db_path).parent / "life.db")
    s.add_contact("Mario Rossi", kind="client")
    reply = json.dumps({"kind": "job", "title": "Inviare il preventivo", "contact_name": "Rossi", "due": "2026-10-23", "notes": ""})
    p = capture.propose(ws, s, "Rossi vuole il preventivo entro venerdì", provider=MockProvider(config=ProviderConfig(model="m"), responses=[f"```json\n{reply}\n```"]), now=NOW)
    assert p["status"] == "ok" and p["kind"] == "job" and p["title"] == "Inviare il preventivo"
    assert p["contact"]["new"] is False and p["contact"]["name"] == "Mario Rossi"
    assert dt.datetime.fromtimestamp(p["due_at"]).date() == dt.date(2026, 10, 23)
    assert s.list_jobs() == [], "a proposal is not saved"
    new = capture.propose(ws, s, "x", provider=MockProvider(config=ProviderConfig(model="m"), responses=[json.dumps({"kind": "reminder", "title": "Chiamare Bianchi", "contact_name": "Bianchi", "due": ""})]), now=NOW)
    assert new["contact"] == {"id": None, "name": "Bianchi", "new": True} and new["due_at"] is None
    assert capture.propose(ws, s, "ciao", provider=MockProvider(config=ProviderConfig(model="m"), responses=['{"kind":"none"}']))["status"] == "nothing"
    assert capture.propose(ws, s, "x", provider=MockProvider(config=ProviderConfig(model="m"), responses=["not json"]))["status"] == "nothing"
    assert capture.propose(ws, s, "   ")["status"] == "empty"
    bad_date = capture.propose(ws, s, "x", provider=MockProvider(config=ProviderConfig(model="m"), responses=[json.dumps({"kind": "job", "title": "T", "due": "tra poco"})]))
    assert bad_date["status"] == "ok" and bad_date["due_at"] is None, "an unreadable date is dropped, never guessed"


def test_routes_round_trip_with_the_memory_mirror(ws):
    c = asyncio.run(routes.life_contacts_create(_req("POST"), routes.ContactPayload(name="Mario Rossi", kind="client")))
    assert c["memory_id"] and ws.memory.get_memory(c["memory_id"], workspace_id=ws.id)
    j = asyncio.run(routes.life_jobs_create(_req("POST"), routes.JobPayload(title="Preventivo", contact_id=c["id"], due_at=time.time() + 86400)))
    done = asyncio.run(routes.life_jobs_update(_req("PATCH"), j["id"], routes.JobPayload(status="done")))
    assert done["status"] == "done"
    r = asyncio.run(routes.life_reminders_create(_req("POST"), routes.ReminderPayload(text="Chiamare", due_at=time.time() - 60)))
    assert asyncio.run(routes.life_reminders_done(_req("POST"), r["id"]))["done"] is True
    today = asyncio.run(routes.life_today(_req(), "it"))
    assert today["counts"]["events"] == 0 and "brief" in today
    with pytest.raises(HTTPException) as e:
        asyncio.run(routes.life_contacts_create(_req("POST"), routes.ContactPayload(name=" ")))
    assert e.value.status_code == 422
    with pytest.raises(HTTPException) as e2:
        asyncio.run(routes.life_jobs_update(_req("PATCH"), "jb-nope", routes.JobPayload(title="x")))
    assert e2.value.status_code == 404
    assert asyncio.run(routes.life_contacts_delete(_req("DELETE"), c["id"]))["deleted"] is True
    assert ws.memory.get_memory(c["memory_id"], workspace_id=ws.id) is None or ws.memory.get_memory(c["memory_id"], workspace_id=ws.id).is_deleted
