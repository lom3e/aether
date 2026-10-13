"""
Tests for Google Calendar Multi-Calendar Resolution, Academic Schedule Discovery,
and Natural Conversational Answers (Macro-pass P0.2 & Assistant-First V2).
"""
from datetime import datetime, timezone, timedelta
import pytest
from unittest.mock import MagicMock, patch

from aether.connections.google_calendar import GoogleCalendarConnector
from aether.personal.service import (
    PersonalAgentService,
    resolve_calendar_time_window,
    format_event_time,
    format_calendar_response,
)
from aether.personal.models import IntentTier


# ---------------------------------------------------------------------------
# 1. Date Window & Weekday Resolution Tests
# ---------------------------------------------------------------------------

def test_resolve_calendar_time_window_weekdays():
    # Fix reference date: Friday, Oct 9, 2026, 15:00 UTC+2
    tz_rome = timezone(timedelta(hours=2))
    ref_dt = datetime(2026, 10, 9, 15, 0, 0, tzinfo=tz_rome)

    # 1. "lunedì" -> Monday, Oct 12, 2026
    t_min, t_max, scope, label = resolve_calendar_time_window("che lezioni ho lunedi all'università?", ref_dt=ref_dt)
    assert scope == "lunedì"
    assert "lunedì 12 ottobre" in label
    assert t_min.startswith("2026-10-12T00:00:00")
    assert t_max.startswith("2026-10-12T23:59:59")

    # 2. "domani" -> Saturday, Oct 10, 2026
    t_min, t_max, scope, label = resolve_calendar_time_window("cosa ho da fare domani?", ref_dt=ref_dt)
    assert scope == "tomorrow"
    assert "domani" in label
    assert t_min.startswith("2026-10-10T00:00:00")
    assert t_max.startswith("2026-10-10T23:59:59")

    # 3. "oggi" -> Friday, Oct 9, 2026
    t_min, t_max, scope, label = resolve_calendar_time_window("cosa ho in programma oggi?", ref_dt=ref_dt)
    assert scope == "today"
    assert t_min.startswith("2026-10-09T00:00:00")
    assert t_max.startswith("2026-10-09T23:59:59")

    # 4. "prossima settimana" -> Oct 12 to Oct 18, 2026
    t_min, t_max, scope, label = resolve_calendar_time_window("quali lezioni ho la prossima settimana?", ref_dt=ref_dt)
    assert scope == "next_week"
    assert t_min.startswith("2026-10-12T00:00:00")
    assert t_max.startswith("2026-10-18T23:59:59")


# ---------------------------------------------------------------------------
# 2. Academic Intent Classification Tests
# ---------------------------------------------------------------------------

def test_academic_intent_classification():
    service = PersonalAgentService(
        store=MagicMock(),
        event_hub=MagicMock(),
        task_manager=MagicMock(),
        action_executor=MagicMock(),
        runtime=MagicMock(),
        activity_service=MagicMock(),
    )

    # Academic queries must be classified as calendar.list_events
    queries = [
        "che lezioni ho lunedi all'università?",
        "Che lezione ho all'uni lunedì?",
        "Quali corsi ho domani?",
        "Mostrami l'orario delle lezioni per martedì",
        "Che impegni ho lunedì all'università?",
    ]

    for q in queries:
        intent = service.classify_intent(q)
        assert intent.tier == IntentTier.ANSWER, f"Failed for {q}"
        assert intent.action_id == "calendar.list_events", f"Failed for {q}"
        assert intent.action_args.get("is_academic") is True, f"Failed for {q}"
        assert intent.action_args.get("time_min") is not None, f"Failed for {q}"
        assert intent.action_args.get("time_max") is not None, f"Failed for {q}"


# ---------------------------------------------------------------------------
# 3. Multi-Calendar Retrieval & Deduplication Tests
# ---------------------------------------------------------------------------

def test_multi_calendar_retrieval_and_deduplication():
    connector = GoogleCalendarConnector(
        auth_metadata={"access_token": "mock-token", "refresh_token": "mock-refresh"},
        workspace_id="test-ws",
    )

    calendars_mock = [
        {"id": "primary", "summary": "Personal Calendar", "primary": True, "accessRole": "owner"},
        {"id": "unito@cineca.it", "summary": "Orario Universitario", "primary": False, "accessRole": "reader"},
        {"id": "busy@shared.com", "summary": "Busy Calendar", "primary": False, "accessRole": "freeBusyReader"},
    ]

    def mock_fetch(calendar_id, limit=50, time_min=None, time_max=None, query=None):
        if calendar_id == "primary":
            return [
                {
                    "id": "evt-1",
                    "title": "Pranzo con Marco",
                    "start_time": "2026-10-12T12:00:00Z",
                    "end_time": "2026-10-12T13:00:00Z",
                    "location": "Mensa",
                }
            ]
        elif calendar_id == "unito@cineca.it":
            return [
                {
                    "id": "evt-lecture-1",
                    "title": "FDA B - FONDAMENTI DELL'INFORMATICA",
                    "start_time": "2026-10-12T07:00:00Z",
                    "end_time": "2026-10-12T09:00:00Z",
                    "location": "Aula B - Dipartimento di Informatica",
                },
                {
                    "id": "evt-lecture-2",
                    "title": "Prog I B - PROGRAMMAZIONE I",
                    "start_time": "2026-10-12T12:00:00Z",
                    "end_time": "2026-10-12T15:00:00Z",
                    "location": "Lab Turing",
                },
            ]
        return []

    connector.list_calendars = MagicMock(return_value=calendars_mock)
    connector._fetch_calendar_events_raw = MagicMock(side_effect=mock_fetch)

    # Multi-calendar search across all accessible calendars
    events = connector.list_events_multi_calendar(time_min="2026-10-12T00:00:00Z", time_max="2026-10-12T23:59:59Z")

    # Should find all 3 events (1 personal, 2 university lectures)
    assert len(events) == 3
    # Verify freeBusyReader was skipped
    assert connector._fetch_calendar_events_raw.call_count == 2

    titles = [e["title"] for e in events]
    assert "FDA B - FONDAMENTI DELL'INFORMATICA" in titles
    assert "Prog I B - PROGRAMMAZIONE I" in titles
    assert "Pranzo con Marco" in titles

    # Verify university events are tagged with calendar_summary
    lecture_ev = next(e for e in events if e["id"] == "evt-lecture-1")
    assert lecture_ev["calendar_summary"] == "Orario Universitario"
    assert lecture_ev["is_primary"] is False

    # Regression check: primary-only search would have missed both university classes!
    primary_events = mock_fetch("primary")
    assert len(primary_events) == 1
    assert "FDA B - FONDAMENTI DELL'INFORMATICA" not in [e["title"] for e in primary_events]


def test_multi_calendar_fault_tolerance():
    connector = GoogleCalendarConnector(
        auth_metadata={"access_token": "mock-token"},
        workspace_id="test-ws",
    )

    calendars_mock = [
        {"id": "cal-faulty", "summary": "Unshared Broken Calendar", "accessRole": "reader"},
        {"id": "cal-good", "summary": "Orario Universitario", "accessRole": "reader"},
    ]

    def mock_fetch(calendar_id, **kwargs):
        if calendar_id == "cal-faulty":
            raise RuntimeError("403 Forbidden")
        return [{"id": "ev-ok", "title": "Algoritmi", "start_time": "2026-10-12T08:00:00Z"}]

    connector.list_calendars = MagicMock(return_value=calendars_mock)
    connector._fetch_calendar_events_raw = MagicMock(side_effect=mock_fetch)

    # Should not crash; faulty calendar is skipped, good calendar events are returned
    events = connector.list_events_multi_calendar()
    assert len(events) == 1
    assert events[0]["title"] == "Algoritmi"


# ---------------------------------------------------------------------------
# 4. Natural Italian Response Formatting Tests
# ---------------------------------------------------------------------------

def test_natural_italian_response_formatting():
    tz_rome = timezone(timedelta(hours=2))

    events = [
        {
            "id": "e1",
            "title": "FDA B - FONDAMENTI DELL'INFORMATICA",
            "start_time": "2026-10-12T07:00:00Z",  # 09:00 CEST
            "end_time": "2026-10-12T09:00:00Z",    # 11:00 CEST
            "location": "Aula B - Via Pessinetto 12",
            "calendar_summary": "Orario Universitario",
        },
        {
            "id": "e2",
            "title": "Prog I B - PROGRAMMAZIONE I",
            "start_time": "2026-10-12T12:00:00Z",  # 14:00 CEST
            "end_time": "2026-10-12T15:00:00Z",    # 17:00 CEST
            "location": "Lab Turing",
            "calendar_summary": "Orario Universitario",
        },
        {
            "id": "e3",
            "title": "Dentista",
            "start_time": "2026-10-12T16:00:00Z",
            "end_time": "2026-10-12T17:00:00Z",
            "calendar_summary": "Personale",
        },
    ]

    resp = format_calendar_response(
        events=events,
        scope="lunedì",
        target_day_label="lunedì 12 ottobre",
        is_academic=True,
        tzinfo=tz_rome,
    )

    # Assertions on response quality:
    assert "Lunedì 12 ottobre hai 2 lezioni in programma:" in resp
    assert "- **FDA B - FONDAMENTI DELL'INFORMATICA** — 09:00 – 11:00 (Aula B - Via Pessinetto 12)" in resp
    assert "- **Prog I B - PROGRAMMAZIONE I** — 14:00 – 17:00 (Lab Turing)" in resp
    assert "altro impegno" in resp  # Mentions personal commitment note
    assert "PDF" not in resp  # Zero requests for manual PDF upload
    assert "incolla" not in resp  # Zero requests to paste text


def test_empty_calendar_response_formatting():
    resp = format_calendar_response(
        events=[],
        scope="lunedì",
        target_day_label="lunedì 12 ottobre",
        is_academic=True,
    )
    assert resp == "Non risultano lezioni in programma per lunedì 12 ottobre sul tuo calendario."
