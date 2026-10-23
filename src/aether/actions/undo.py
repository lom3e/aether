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
REVERSIBLE_ACTIONS = {"files.create_document"} | CALENDAR_ACTIONS | LIFE_ACTIONS


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
    if execution.action_id in CALENDAR_ACTIONS or execution.action_id in LIFE_ACTIONS:
        done = _undo_calendar(ws, execution, info["kind"]) if execution.action_id in CALENDAR_ACTIONS else _undo_life(ws, execution)
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
