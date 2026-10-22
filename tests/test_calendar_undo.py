"""Undo for calendar changes: the exact inverse, and a refusal when someone changed the event again in the meantime."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from aether.actions import undo as undo_mod


class FakeGoogle:
    def __init__(self, current_start="2026-10-23T15:00:00+02:00"):
        self.calls = []
        self.current_start = current_start

    def delete_event(self, event_id, calendar_id=None):
        self.calls.append(("delete", event_id, calendar_id))

    def get_event(self, event_id, calendar_id=None):
        return {"id": event_id, "start_time": self.current_start}

    def update_event(self, event_id, start_time=None, end_time=None, calendar_id=None, **kw):
        self.calls.append(("update", event_id, start_time, end_time))

    def create_event(self, title, start_time, end_time=None, location="", calendar_id=None, **kw):
        self.calls.append(("create", title, start_time, end_time, calendar_id))
        return {"event_id": "new-" + title}


class Store:
    def __init__(self, ex):
        self.ex = ex

    def get_execution(self, i):
        return self.ex if i == self.ex.id else None

    def save_execution(self, ex):
        self.ex = ex


def _ws(ex, google):
    return SimpleNamespace(action_store=Store(ex), connections=SimpleNamespace(get_google_calendar_connector=lambda ws_id: google))


def _ex(action_id, inp, out):
    return SimpleNamespace(id="x1", workspace_id="ws", action_id=action_id, input_data=inp, output_data=out, metadata={}, created_at="2026-10-22T10:00:00Z")


def test_an_event_aether_created_is_removed():
    g = FakeGoogle()
    ex = _ex("google_calendar.create_event", {"title": "Dentista"}, {"event_id": "e1", "title": "Dentista"})
    assert undo_mod.describe(None, ex)["kind"] == "remove_event"
    assert undo_mod.undo(_ws(ex, g), "x1")["result"] == "removed"
    assert g.calls == [("delete", "e1", None)]
    with pytest.raises(undo_mod.UndoError) as e:
        undo_mod.undo(_ws(ex, g), "x1")
    assert e.value.code == "already_undone"


def test_a_moved_event_goes_back_unless_it_was_moved_again():
    inp = {"event_id": "e2", "title": "Riunione", "start_time": "2026-10-23T15:00:00+02:00", "end_time": "2026-10-23T16:00:00+02:00",
           "previous": {"start_time": "2026-10-22T11:00:00+02:00", "end_time": "2026-10-22T12:00:00+02:00"}}
    g = FakeGoogle(current_start="2026-10-23T13:00:00Z")  # same instant as 15:00+02:00
    assert undo_mod.undo(_ws(_ex("google_calendar.update_event", inp, {}), g), "x1")["result"] == "moved_back"
    assert g.calls == [("update", "e2", "2026-10-22T11:00:00+02:00", "2026-10-22T12:00:00+02:00")]
    moved_again = FakeGoogle(current_start="2026-10-24T09:00:00+02:00")
    with pytest.raises(undo_mod.UndoError) as e:
        undo_mod.undo(_ws(_ex("google_calendar.update_event", inp, {}), moved_again), "x1")
    assert e.value.code == "changed_since" and moved_again.calls == []


def test_a_deleted_event_is_created_again_from_the_kept_copy():
    out = {"deleted": 1, "events": [{"event_id": "e3", "calendar_id": "uni", "title": "Analisi 1", "start_time": "2026-10-23T08:00:00+02:00", "end_time": "2026-10-23T10:00:00+02:00"}]}
    g = FakeGoogle()
    res = undo_mod.undo(_ws(_ex("google_calendar.delete_event", {}, out), g), "x1")
    assert res["result"] == "recreated" and res["event_ids"] == ["new-Analisi 1"]
    assert g.calls == [("create", "Analisi 1", "2026-10-23T08:00:00+02:00", "2026-10-23T10:00:00+02:00", "uni")]


def test_without_a_kept_copy_it_says_so():
    item = undo_mod.describe(None, _ex("google_calendar.delete_event", {}, {"deleted": 1, "events": []}))
    assert item["reversible"] is False and item["reason"] == "missing_backup"
