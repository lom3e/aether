"""
Undo for what Aether did to the user's files.

Only actions whose inverse is known and checkable are offered: a document Aether created (the inverse is deleting it)
or overwrote (the inverse is putting the previous version back). Every undo refuses when the file has been changed since
Aether wrote it (the user's later work is never destroyed), keeps what it replaces in the hidden history folder, and is
itself recorded on the execution. Everything else is listed as "cannot be undone" rather than pretending.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
from pathlib import Path
from typing import Any

REVERSIBLE_ACTIONS = {"files.create_document"}


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
