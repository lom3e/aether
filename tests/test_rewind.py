"""Rewind: one timeline of every change Aether made, across services, and "put everything back as it was before this"
(newest first). Reads never appear; what cannot be undone is listed with its reason, never skipped silently."""
from __future__ import annotations

from types import SimpleNamespace

from aether.actions import undo as undo_mod
from aether.actions.models import ActionExecution, ActionExecutionStatus
from aether.life.store import life_store_for
from aether.workspace.workspace import Workspace


class FakeGmail:
    def __init__(self):
        self.trashed = {"m1"}

    def untrash(self, ids):
        self.trashed -= set(ids)
        return list(ids)


def _record(ws, eid, action_id, created_at, inp=None, out=None):
    ex = ActionExecution(id=eid, action_id=action_id, workspace_id=ws.id, status=ActionExecutionStatus.SUCCEEDED,
                         input_data=inp or {}, output_data=out or {}, created_at=created_at)
    ws.action_store.save_execution(ex)
    return ex


def test_timeline_lists_changes_not_reads_and_rewind_takes_back_newest_first(tmp_path, monkeypatch):
    ws = Workspace.init(tmp_path, name="rewind")
    try:
        store = life_store_for(ws)
        c = store.add_contact("Rossi", kind="client")
        j = store.add_job("Inviare il preventivo", contact_id=c["id"])
        gmail = FakeGmail()
        monkeypatch.setattr(ws.connections, "get_gmail_connector", lambda ws_id: gmail)

        _record(ws, "ex-read", "gmail.search", "2026-10-24T09:00:00+00:00", {"query": "is:unread"})
        _record(ws, "ex-life", "life.save", "2026-10-24T10:00:00+00:00", {"kind": "job", "title": "Inviare il preventivo", "contact_name": "Rossi"},
                {"job_id": j["id"], "created_contact_id": c["id"], "contact_id": c["id"]})
        _record(ws, "ex-sent", "gmail.send", "2026-10-24T11:00:00+00:00", {"to": "a@b.c", "subject": "Ciao"}, {"draft_id": "d1", "sent": True})
        _record(ws, "ex-trash", "gmail.trash", "2026-10-24T12:00:00+00:00", {"messages": [{"id": "m1", "subject": "Saldi"}]}, {"trashed": ["m1"]})

        items = undo_mod.timeline(ws, ws.id)
        assert [i["execution_id"] for i in items] == ["ex-trash", "ex-sent", "ex-life"], "newest first, reads left out"
        assert {i["execution_id"]: i["service"] for i in items} == {"ex-trash": "gmail", "ex-sent": "gmail", "ex-life": "life"}
        sent = next(i for i in items if i["execution_id"] == "ex-sent")
        assert not sent["reversible"] and sent["reason"] == "already_sent"

        result = undo_mod.rewind(ws, ws.id, "ex-life")
        assert [u["execution_id"] for u in result["undone"]] == ["ex-trash", "ex-life"]
        assert result["kept"] == [{"execution_id": "ex-sent", "title": "Ciao", "reason": "already_sent"}]
        assert gmail.trashed == set() and store.list_jobs() == [] and store.list_contacts() == []
        again = undo_mod.timeline(ws, ws.id)
        assert all(i["undone"] for i in again if i["execution_id"] != "ex-sent")
        assert undo_mod.rewind(ws, ws.id, "ex-life") == {"undone": [], "kept": [{"execution_id": "ex-sent", "title": "Ciao", "reason": "already_sent"}]}
    finally:
        ws.close()


def test_the_rewind_routes_answer_on_the_real_server(aether_server):
    import json
    import urllib.error
    import urllib.request

    headers = {"Authorization": f"Bearer {aether_server['token']}"} if aether_server.get("token") else {}
    with urllib.request.urlopen(urllib.request.Request(f"{aether_server['base_url']}/api/undo/timeline", headers=headers), timeout=10) as r:
        assert r.status == 200 and isinstance(json.loads(r.read())["items"], list)
    try:
        urllib.request.urlopen(urllib.request.Request(f"{aether_server['base_url']}/api/undo/rewind/does-not-exist", method="POST", headers=headers), timeout=10)
        raise AssertionError("expected 404")
    except urllib.error.HTTPError as exc:
        assert exc.code == 404
