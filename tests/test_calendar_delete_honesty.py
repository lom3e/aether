"""Deleting calendar events: recognised, resolved against the real calendar, confirmed by the user, never faked in text."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from aether.actions.models import ActionExecutionStatus
from aether.actions.registry import ActionRegistry
from aether.personal.models import IntentTier
from aether.personal.service import (
    PersonalAgentService,
    dedupe_calendar_events,
    format_calendar_response,
    match_calendar_events,
    parse_calendar_delete_request,
)

LISTING = (
    "Ecco i tuoi impegni in programma per domani:\n\n"
    "- **Controllare tasse UniTo** — 10:00 – 11:00\n"
    "- **Compilazione Piano Carriera MyUniTo** — 17:00 – 18:00"
)
HISTORY = [SimpleNamespace(role="user", content="che impegni ho domani?"), SimpleNamespace(role="assistant", content=LISTING)]


def _svc():
    return object.__new__(PersonalAgentService)


def test_the_google_calendar_actions_are_registered_and_need_confirmation():
    reg = ActionRegistry()
    for aid in ("google_calendar.delete_event", "google_calendar.update_event", "google_calendar.create_event"):
        d = reg.get(aid)
        assert d is not None and d.requires_confirmation and d.tier.value == "act"


def test_parse_quoted_title_plural_reference_and_non_calendar_sentences():
    assert parse_calendar_delete_request('cancella “Compilazione Piano Carriera MyUniTo”', HISTORY) == ["Compilazione Piano Carriera MyUniTo"]
    assert parse_calendar_delete_request("puoi cancellarli? li ho completati entrambi", HISTORY) == ["Controllare tasse UniTo", "Compilazione Piano Carriera MyUniTo"]
    assert parse_calendar_delete_request("cancella l'appuntamento dentista dal calendario", None) == ["dentista"]
    # not about the calendar: a file or a memory must never be treated as a calendar deletion
    assert parse_calendar_delete_request("cancella il file notes.txt", None) is None
    assert parse_calendar_delete_request("cancellali", [SimpleNamespace(role="assistant", content="Fatto, ho scritto la mail.")]) is None
    assert parse_calendar_delete_request("che impegni ho domani?", HISTORY) is None


def test_intent_is_act_tier_so_it_needs_approval():
    intent = _svc()._classify_intent_rules('cancella “Controllare tasse UniTo”', recent_history=HISTORY)
    assert intent.tier == IntentTier.ACT and intent.action_id == "google_calendar.delete_event"
    assert intent.action_args["target_titles"] == ["Controllare tasse UniTo"]


def _ev(i, title, start, cal="UNI", primary=False):
    return {"id": i, "calendar_id": cal, "title": title, "start_time": start.isoformat(), "end_time": (start + timedelta(hours=1)).isoformat(), "calendar_summary": cal, "is_primary": primary}


def test_match_picks_the_next_upcoming_occurrence_and_counts_the_rest():
    now = datetime.now(timezone.utc)
    evs = [_ev("a", "Piano Carriera", now + timedelta(days=1)), _ev("b", "Piano Carriera", now + timedelta(days=2)), _ev("c", "Altro", now + timedelta(days=1))]
    got = match_calendar_events(evs, ["piano carriera"], now)
    assert [e["id"] for e in got] == ["a"] and got[0]["_same_title_count"] == 2


class _Exec:
    def __init__(self, status, provider="google_calendar", events=None, error=""):
        self.r = SimpleNamespace(status=status, output_data={"provider": provider, "events": events or []}, error_message=error)
        self.calls = []

    def execute(self, **kw):
        self.calls.append(kw["action_id"])
        return self.r


def test_resolution_builds_the_exact_confirmation_and_deletes_nothing_by_itself():
    now = datetime.now(timezone.utc)
    s = _svc()
    s.action_executor = _Exec(ActionExecutionStatus.SUCCEEDED, events=[_ev("a", "Controllare tasse UniTo", now + timedelta(days=1))])
    intent = _svc()._classify_intent_rules('cancella “Controllare tasse UniTo”', recent_history=HISTORY)
    intent, explain = s._resolve_calendar_deletion(intent, "ws")
    assert explain == "" and intent.action_args["events"][0]["event_id"] == "a" and intent.action_args["events"][0]["when"]
    assert s.action_executor.calls == ["calendar.list_events"], "resolving only reads; the deletion waits for the user's confirmation"


def test_honest_messages_when_nothing_matches_or_google_is_not_connected():
    now = datetime.now(timezone.utc)
    intent = _svc()._classify_intent_rules('cancella “Controllare tasse UniTo”', recent_history=HISTORY)
    s = _svc()
    s.action_executor = _Exec(ActionExecutionStatus.SUCCEEDED, events=[_ev("a", "Dentista", now + timedelta(days=1))])
    _, msg = s._resolve_calendar_deletion(intent, "ws")
    assert "Non trovo" in msg and "Non ho cancellato nulla" in msg
    s.action_executor = _Exec(ActionExecutionStatus.SUCCEEDED, provider="calendar")
    _, msg = s._resolve_calendar_deletion(intent, "ws")
    assert "Google Calendar" in msg and "Non ho cancellato nulla" in msg
    s.action_executor = _Exec(ActionExecutionStatus.FAILED, error="boom")
    _, msg = s._resolve_calendar_deletion(intent, "ws")
    assert "non cancello nulla" in msg


def test_listing_shows_the_day_of_each_event_and_hides_duplicates():
    now = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
    evs = [_ev("a", "Piano Carriera", now), _ev("b", "Piano Carriera", now), _ev("c", "Piano Carriera", now + timedelta(days=1))]
    assert len(dedupe_calendar_events(evs)) == 2
    text = format_calendar_response(events=evs, scope="upcoming", target_day_label=None, is_academic=True, tzinfo=timezone.utc)
    assert "**Giovedì 22 ottobre**" in text and "**Venerdì 23 ottobre**" in text
    assert "lezioni" not in text, "a personal calendar named UNI holds tasks, not lessons"


def test_deleting_runs_only_after_approval_and_reports_what_was_removed(tmp_path, accepted_authority_factory):
    """Through the real executor: the deletion waits for the user, then removes exactly the confirmed events."""
    from aether.connections.models import ConnectionStatus
    from aether.workspace.workspace import Workspace

    ws = Workspace(root=tmp_path)
    removed = []

    class FakeGoogle:
        def delete_event(self, event_id, calendar_id=None):
            removed.append((event_id, calendar_id))
            return True

    ws.connections.get_connection = lambda ws_id, provider: SimpleNamespace(status=ConnectionStatus.VERIFIED, auth_metadata={"refresh_token": "x"}, last_verification_error="")  # type: ignore[method-assign]
    ws.connections.get_google_calendar_connector = lambda ws_id: FakeGoogle()  # type: ignore[method-assign]
    ws.connections.record_operation_success = lambda *a, **k: None  # type: ignore[method-assign]
    _, auth = accepted_authority_factory(ws, title="Delete events")
    args = {"events": [{"event_id": "e1", "calendar_id": "uni", "title": "Piano Carriera", "start_time": "2026-10-22T17:00:00+02:00"}]}
    res = ws.actions.execute("google_calendar.delete_event", ws.id, args, authority=auth)
    assert res.status == ActionExecutionStatus.WAITING_APPROVAL and removed == [], "nothing is deleted before the user confirms"
    res = ws.actions.approve(res.id)
    assert res.status == ActionExecutionStatus.SUCCEEDED
    assert removed == [("e1", "uni")] and res.output_data["deleted"] == 1 and res.output_data["events"][0]["title"] == "Piano Carriera"
