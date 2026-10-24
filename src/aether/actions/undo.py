"""
Undo for what Aether did to the user's files and calendar.

Only actions whose inverse is known and checkable are offered: a document Aether created (the inverse is deleting it)
or overwrote (the inverse is putting the previous version back). Every undo refuses when the file has been changed since
Aether wrote it (the user's later work is never destroyed), keeps what it replaces in the hidden history folder, and is
itself recorded on the execution. Everything else is listed as "cannot be undone" rather than pretending.

Calendar changes made through Google Calendar have exact inverses too: an event Aether created is removed, an event it
moved goes back to its previous time (only if nobody moved it again since), an event it deleted is created again from the
copy kept when it was deleted.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
from pathlib import Path
from typing import Any

CALENDAR_ACTIONS = {"google_calendar.create_event", "google_calendar.update_event", "google_calendar.delete_event"}
LIFE_ACTIONS = {"life.save"}
GMAIL_ACTIONS = {"gmail.create_draft", "gmail.send", "gmail.trash", "gmail.modify_labels"}
GITHUB_ACTIONS = {"github.create_issue"}
REVERSIBLE_ACTIONS = {"files.create_document"} | CALENDAR_ACTIONS | LIFE_ACTIONS | GMAIL_ACTIONS | GITHUB_ACTIONS


class UndoError(Exception):
    """``code``: not_found | not_reversible | already_undone | changed_since | missing_backup | outside_workspace | failed."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _target(ws: Any, execution: Any) -> tuple[Path, Path]:
    """(sandboxed target path, history dir) for a document execution."""
    from aether.core.security import PathSandbox

    base = ws.action_executor._user_files_base(ws)
    filename = (execution.input_data or {}).get("filename") or (execution.output_data or {}).get("filename") or ""
    try:
        target = PathSandbox(base, auto_create=True).resolve(filename)
    except Exception as exc:  # noqa: BLE001
        raise UndoError("outside_workspace", str(exc)) from exc
    return target, Path(base) / ".aether-versions"


def describe(ws: Any, execution: Any) -> dict[str, Any]:
    out = execution.output_data or {}
    item: dict[str, Any] = {
        "execution_id": execution.id,
        "action_id": execution.action_id,
        "title": (execution.input_data or {}).get("filename") or execution.action_id,
        "created_at": execution.created_at,
        "reversible": False,
        "reason": "",
        "undone": bool((execution.metadata or {}).get("undo")),
        "effect": out.get("status") or "",
    }
    if execution.action_id not in REVERSIBLE_ACTIONS:
        item["reason"] = "no_undo"
        return item
    if item["undone"]:
        item["reason"] = "already_undone"
        return item
    if execution.action_id in CALENDAR_ACTIONS:
        return _describe_calendar(execution, item)
    if execution.action_id in GMAIL_ACTIONS:
        out_, inp_ = execution.output_data or {}, execution.input_data or {}
        msgs = inp_.get("messages") or []
        item["title"] = inp_.get("subject") or ", ".join(m.get("subject", "") for m in msgs[:3] if m.get("subject")) or item["title"]
        if execution.action_id == "gmail.send":
            from aether.actions import mail_send

            if out_.get("draft_id") and mail_send.is_pending(out_["draft_id"]):
                item["reversible"], item["kind"] = True, "unsend"
            else:
                item["reason"] = "already_sent"
            return item
        kind = {"gmail.create_draft": "remove_draft", "gmail.trash": "untrash", "gmail.modify_labels": "relabel"}[execution.action_id]
        ok = bool(out_.get("draft_id")) if kind == "remove_draft" else bool(out_.get("trashed") or out_.get("ids"))
        if ok:
            item["reversible"], item["kind"] = True, kind
        else:
            item["reason"] = "missing_backup"
        return item
    if execution.action_id in GITHUB_ACTIONS:
        out_ = execution.output_data or {}
        item["title"] = out_.get("title") or (execution.input_data or {}).get("title") or item["title"]
        if out_.get("number"):
            item["reversible"], item["kind"] = True, "close_issue"
        else:
            item["reason"] = "missing_backup"
        return item
    if execution.action_id in LIFE_ACTIONS:
        out_, inp_ = execution.output_data or {}, execution.input_data or {}
        item["title"] = inp_.get("title") or inp_.get("contact_name") or item["title"]
        if out_.get("job_id") or out_.get("reminder_id") or out_.get("created_contact_id"):
            item["reversible"], item["kind"] = True, "remove_note"
        else:
            item["reason"] = "missing_backup"
        return item
    try:
        target, _ = _target(ws, execution)
    except UndoError as exc:
        item["reason"] = exc.code
        return item
    recorded = out.get("sha256")
    if not target.exists():
        item["reason"] = "changed_since"
    elif recorded and _sha(target) != recorded:
        item["reason"] = "changed_since"
    elif out.get("status") == "updated" and not (out.get("previous_version") and Path(out["previous_version"]).is_file()):
        item["reason"] = "missing_backup"
    elif not recorded:
        item["reason"] = "no_undo"  # written before checksums existed: not provably unchanged
    else:
        item["reversible"] = True
        item["kind"] = "restore" if out.get("status") == "updated" else "delete"
    return item


def _describe_calendar(execution: Any, item: dict[str, Any]) -> dict[str, Any]:
    inp, out = execution.input_data or {}, execution.output_data or {}
    if execution.action_id == "google_calendar.create_event":
        item["title"] = out.get("title") or inp.get("title") or item["title"]
        ok, kind = bool(out.get("event_id") or out.get("id")), "remove_event"
    elif execution.action_id == "google_calendar.update_event":
        item["title"] = inp.get("title") or item["title"]
        prev = inp.get("previous") or {}
        ok, kind = bool(inp.get("event_id") and prev.get("start_time")), "move_back"
    else:
        events = out.get("events") or []
        item["title"] = ", ".join(e.get("title", "") for e in events if e.get("title")) or item["title"]
        ok, kind = bool(events) and all(e.get("start_time") for e in events), "recreate"
    if ok:
        item["reversible"], item["kind"] = True, kind
    else:
        item["reason"] = "missing_backup"
    return item


def _undo_calendar(ws: Any, execution: Any, kind: str) -> dict[str, Any]:
    inp, out = execution.input_data or {}, execution.output_data or {}
    connector = ws.connections.get_google_calendar_connector(execution.workspace_id)
    try:
        if kind == "remove_event":
            connector.delete_event(event_id=out.get("event_id") or out.get("id"), calendar_id=inp.get("calendar_id"))
            return {"result": "removed"}
        if kind == "move_back":
            current = connector.get_event(event_id=inp["event_id"], calendar_id=inp.get("calendar_id")) or {}
            now_start = str(current.get("start_time") or "")
            if now_start and inp.get("start_time") and _same_instant(now_start, inp["start_time"]) is False:
                raise UndoError("changed_since", "the event was moved again after Aether moved it")
            prev = inp.get("previous") or {}
            connector.update_event(event_id=inp["event_id"], start_time=prev.get("start_time"), end_time=prev.get("end_time"), calendar_id=inp.get("calendar_id"))
            return {"result": "moved_back"}
        recreated = []
        for e in out.get("events") or []:
            made = connector.create_event(title=e.get("title", ""), start_time=e["start_time"], end_time=e.get("end_time"), location=e.get("location", ""), calendar_id=e.get("calendar_id"))
            recreated.append(made.get("event_id") or made.get("id"))
        return {"result": "recreated", "event_ids": recreated}
    except UndoError:
        raise
    except Exception as exc:  # noqa: BLE001 - a calendar error must surface as a refusal, not a 500
        raise UndoError("failed", str(exc)) from exc


def _undo_gmail(ws: Any, execution: Any, kind: str) -> dict[str, Any]:
    from aether.connections.gmail import LABEL_OPS

    out = execution.output_data or {}
    if kind == "unsend":
        from aether.actions import mail_send

        if not mail_send.cancel(out.get("draft_id", "")):
            raise UndoError("already_sent", "the email already left")
        return {"result": "unsent", "draft_kept": True}
    connector = ws.connections.get_gmail_connector(execution.workspace_id)
    try:
        if kind == "remove_draft":
            if not connector.draft_exists(out["draft_id"]):
                raise UndoError("changed_since", "the draft was sent or deleted in Gmail since")
            connector.delete_draft(out["draft_id"])
            return {"result": "draft_removed"}
        if kind == "untrash":
            return {"result": "untrashed", "ids": connector.untrash(list(out.get("trashed") or []))}
        add, remove = LABEL_OPS[out.get("op", "")]
        connector.modify_labels(list(out.get("ids") or []), add=remove, remove=add)  # the exact inverse
        return {"result": "relabelled"}
    except UndoError:
        raise
    except Exception as exc:  # noqa: BLE001 - a Gmail error must surface as a refusal, not a 500
        raise UndoError("failed", str(exc)) from exc


def _undo_github(ws: Any, execution: Any) -> dict[str, Any]:
    out, inp = execution.output_data or {}, execution.input_data or {}
    connector = ws.connections.get_github_connector(execution.workspace_id)
    res = connector.execute("github.update_issue", {"full_name": inp.get("full_name"), "owner": inp.get("owner"), "repository": inp.get("repository"),
                                                    "issue_number": out["number"], "state": "closed"})
    if hasattr(res, "success") and not res.success:
        raise UndoError("failed", getattr(res, "error", "") or "could not close the issue")
    return {"result": "closed", "number": out["number"]}


def _undo_life(ws: Any, execution: Any) -> dict[str, Any]:
    """Takes back what one confirmed note saved: the job or reminder, and the client only if this note created it and
    nothing else hangs on it since."""
    from aether.life import service as life
    from aether.life.store import life_store_for

    out = execution.output_data or {}
    store = life_store_for(ws)
    removed: list[str] = []
    if out.get("job_id") and store.get_job(out["job_id"]):
        life.forget_job(ws, store, out["job_id"])
        removed.append("job")
    if out.get("reminder_id") and store.get_reminder(out["reminder_id"]):
        store.delete_reminder(out["reminder_id"])
        removed.append("reminder")
    cid = out.get("created_contact_id")
    if cid and store.get_contact(cid) and not store.list_jobs(contact_id=cid):
        life.forget_contact(ws, store, cid)
        removed.append("contact")
    return {"result": "removed", "removed": removed}


def _same_instant(a: str, b: str) -> bool | None:
    try:
        return _dt.datetime.fromisoformat(a.replace("Z", "+00:00")) == _dt.datetime.fromisoformat(b.replace("Z", "+00:00"))
    except ValueError:
        return None


def list_items(ws: Any, workspace_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Recent successful actions that changed the user's files (and, for context, why the others cannot be undone)."""
    rows = ws.action_store.list_executions(workspace_id=workspace_id, status="succeeded", limit=max(1, min(limit, 200)))
    return [describe(ws, e) for e in rows if e.action_id in REVERSIBLE_ACTIONS or (e.metadata or {}).get("undo")]


def _changes_something(ws: Any, action_id: str) -> bool:
    if action_id in REVERSIBLE_ACTIONS:
        return True
    try:
        d = ws.action_registry.get(action_id)
    except Exception:  # noqa: BLE001
        d = None
    return bool(d) and str(getattr(d.permission_level, "value", d.permission_level)) != "read_only"


def timeline(ws: Any, workspace_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Rewind: everything Aether changed for you (files, calendar, mail, GitHub, people & jobs), newest first, each with
    whether and how it can be taken back. Reads are left out: they changed nothing."""
    rows = ws.action_store.list_executions(workspace_id=workspace_id, status="succeeded", limit=max(1, min(limit * 3, 600)))
    out = []
    for e in rows:
        if not _changes_something(ws, e.action_id):
            continue
        item = describe(ws, e) if e.action_id in REVERSIBLE_ACTIONS else {
            "execution_id": e.id, "action_id": e.action_id, "title": (e.input_data or {}).get("title") or e.action_id, "created_at": e.created_at,
            "reversible": False, "reason": "no_undo", "undone": bool((e.metadata or {}).get("undo")), "effect": ""}
        item["service"] = e.action_id.split(".", 1)[0]
        out.append(item)
        if len(out) >= limit:
            break
    return out


def rewind(ws: Any, workspace_id: str, execution_id: str) -> dict[str, Any]:
    """Takes back, newest first, every reversible change from the chosen one onwards: "put everything back as it was
    just before this". Changes that cannot be undone are listed, never silently skipped."""
    target = ws.action_store.get_execution(execution_id)
    if target is None:
        raise UndoError("not_found")
    items = [i for i in timeline(ws, workspace_id, limit=200) if str(i["created_at"]) >= str(target.created_at)]
    undone, kept = [], []
    for item in items:  # already newest first
        if item.get("undone"):
            continue
        if not item.get("reversible"):
            kept.append({"execution_id": item["execution_id"], "title": item["title"], "reason": item.get("reason") or "no_undo"})
            continue
        try:
            undo(ws, item["execution_id"])
            undone.append({"execution_id": item["execution_id"], "title": item["title"]})
        except UndoError as exc:
            kept.append({"execution_id": item["execution_id"], "title": item["title"], "reason": exc.code})
    return {"undone": undone, "kept": kept}


def _keep(current: Path, history: Path, suffix: str) -> Path:
    history.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    dest = history / f"{current.name}.{stamp}.{suffix}"
    dest.write_bytes(current.read_bytes())
    return dest


def undo(ws: Any, execution_id: str) -> dict[str, Any]:
    execution = ws.action_store.get_execution(execution_id)
    if execution is None:
        raise UndoError("not_found")
    info = describe(ws, execution)
    if not info["reversible"]:
        raise UndoError(info["reason"] or "not_reversible")
    try:  # an Undo means the user did not want it: earning autonomy for that kind starts over
        from aether.personal.autonomy import autonomy_store_for, key_for

        autonomy_store_for(ws).reset(key_for(execution.action_id, execution.input_data))
    except Exception:  # noqa: BLE001
        pass
    if execution.action_id in CALENDAR_ACTIONS | LIFE_ACTIONS | GMAIL_ACTIONS | GITHUB_ACTIONS:
        if execution.action_id in CALENDAR_ACTIONS:
            done = _undo_calendar(ws, execution, info["kind"])
        elif execution.action_id in GMAIL_ACTIONS:
            done = _undo_gmail(ws, execution, info["kind"])
        elif execution.action_id in GITHUB_ACTIONS:
            done = _undo_github(ws, execution)
        else:
            done = _undo_life(ws, execution)
        execution.metadata = {**(execution.metadata or {}), "undo": {"at": _dt.datetime.now(_dt.timezone.utc).isoformat(), **done}}
        ws.action_store.save_execution(execution)
        return {"execution_id": execution_id, **done}
    target, history = _target(ws, execution)
    out = execution.output_data
    try:
        kept = _keep(target, history, "undone")
        if info["kind"] == "delete":
            target.unlink()
            result = "deleted"
        else:
            previous = Path(out["previous_version"])
            target.write_bytes(previous.read_bytes())
            result = "restored"
    except OSError as exc:
        raise UndoError("failed", str(exc)) from exc
    execution.metadata = {**(execution.metadata or {}), "undo": {"at": _dt.datetime.now(_dt.timezone.utc).isoformat(), "result": result, "kept": str(kept)}}
    ws.action_store.save_execution(execution)
    return {"execution_id": execution_id, "result": result, "path": str(target), "kept": str(kept)}
