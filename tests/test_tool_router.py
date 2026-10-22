"""Model-assisted routing: the model only structures the request; reads run, changes wait for the user's confirmation."""
from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

from aether.actions.models import ActionExecutionStatus
from aether.personal import tool_router
from aether.workspace.workspace import Workspace

NOW = dt.datetime(2026, 10, 22, 10, 0).astimezone()


class Model:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def generate(self, messages):
        self.calls += 1
        return SimpleNamespace(content=self.payload if isinstance(self.payload, str) else json.dumps(self.payload))


def test_route_validates_what_the_model_returns():
    r = tool_router.route("sposta la riunione con Rossi a venerdì alle 15", provider=Model({"action": "calendar_move", "target": "Riunione Rossi", "start": "2026-10-23T15:00"}), now=NOW)
    assert r["action"] == "calendar_move" and r["target"] == "Riunione Rossi" and r["start_time"].startswith("2026-10-23T15:00")
    c = tool_router.route("metti dentista domani", provider=Model({"action": "calendar_create", "title": "Dentista", "start": "2026-10-23"}), now=NOW)
    assert c["start_time"].startswith("2026-10-23T09:00") and c["end_time"].startswith("2026-10-23T10:00"), "no time → 09:00, one hour"
    assert tool_router.route("x", provider=Model({"action": "calendar_create", "title": ""}), now=NOW)["action"] == "none", "incomplete never acts"
    assert tool_router.route("x", provider=Model("not json"), now=NOW)["action"] == "none"
    assert tool_router.route("x", provider=Model({"action": "send_money"}), now=NOW)["action"] == "none", "only known actions"
    assert tool_router.route("x", provider=None)["action"] == "none"


def test_ordinary_chat_does_not_pay_for_a_routing_call():
    assert not tool_router.worth_routing("ciao, come stai?")
    assert not tool_router.worth_routing("spiegami la fotosintesi")
    assert tool_router.worth_routing("la riunione con Rossi spostala a venerdì")


def _event(i, title, start):
    return {"id": i, "calendar_id": "primary", "title": title, "start_time": start.isoformat(), "end_time": (start + dt.timedelta(minutes=90)).isoformat(), "calendar_summary": "Personale", "is_primary": True}


def test_moving_an_event_from_chat_shows_before_and_after_and_waits(tmp_path, monkeypatch):
    ws = Workspace.init(tmp_path, name="router")
    try:
        svc = ws.personal
        tomorrow = (dt.datetime.now().astimezone() + dt.timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0)
        friday = (tomorrow + dt.timedelta(days=1)).replace(hour=15)
        svc._router_provider_override = Model({"action": "calendar_move", "target": "Riunione Rossi", "start": friday.strftime("%Y-%m-%dT%H:%M")})
        monkeypatch.setattr(svc, "_google_calendar_ready", lambda ws_id: True)
        real = svc.action_executor.execute

        def execute(*a, **k):
            if k.get("action_id") == "calendar.list_events":
                return SimpleNamespace(status=ActionExecutionStatus.SUCCEEDED, output_data={"provider": "google_calendar", "events": [_event("r1", "Riunione Rossi", tomorrow)]}, error_message="")
            return real(*a, **k)

        monkeypatch.setattr(svc.action_executor, "execute", execute)
        msg = svc.process_prompt(workspace_id=ws.name, prompt="la riunione con Rossi spostala a dopodomani alle 15")
        assert "Sto per spostare" in msg.content and "Riunione Rossi" in msg.content and "da:" in msg.content and "Mission Proposal" not in msg.content
        assert msg.metadata["status"] == "proposal_pending"
        shown = msg.metadata["resolved_action"]
        assert shown["action_id"] == "google_calendar.update_event"
        args = shown["args"]
        assert args["event_id"] == "r1" and args["start_time"].startswith(friday.strftime("%Y-%m-%dT%H:%M"))
        assert args["end_time"].startswith(friday.replace(hour=16, minute=30).strftime("%Y-%m-%dT%H:%M")), "keeps the 90-minute length"

        # The user accepts; the app re-sends the sentence with the authority. Even if the model would now read it
        # differently, exactly the confirmed action is what goes forward.
        _, authority = svc.accept_proposal(proposal_id=msg.metadata["proposal_id"], workspace_id=ws.id, expected_version=msg.metadata["proposal_version"], actor="user", channel="api")
        svc._router_provider_override = Model({"action": "calendar_delete", "target": "Riunione Rossi"})
        follow = svc.process_prompt(workspace_id=ws.name, prompt="la riunione con Rossi spostala a dopodomani alle 15", session_id=msg.session_id, authority=authority)
        waiting = [s for s in follow.steps if s.status == "waiting_approval"]
        assert waiting and waiting[0].details["action_id"] == "google_calendar.update_event"
        assert waiting[0].details["args"]["event_id"] == "r1"
    finally:
        ws.close()


def test_without_google_a_move_is_refused_honestly(tmp_path, monkeypatch):
    ws = Workspace.init(tmp_path, name="router2")
    try:
        svc = ws.personal
        svc._router_provider_override = Model({"action": "calendar_move", "target": "Riunione Rossi", "start": "2026-10-23T15:00"})
        msg = svc.process_prompt(workspace_id=ws.name, prompt="la riunione con Rossi spostala a venerdì")
        assert "Collegamenti" in msg.content and "Non ho fatto nessuna modifica" in msg.content
        assert not [s for s in msg.steps if s.status == "waiting_approval"]
    finally:
        ws.close()
