"""Undo for what Aether wrote into the user's files: restore, delete, refuse when changed since, never fake."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException, Request

from aether.actions import undo as undo_mod
from aether.actions.models import ActionExecution, ActionExecutionStatus
from aether.server.app import app
from aether.server.routes import undo_apply_route, undo_list_route
from aether.workspace.workspace import Workspace


@pytest.fixture
def ws(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path / "data"))
    w = Workspace.init(tmp_path / "ws", name="Undo Test")
    app.state.workspace = w
    yield w
    w.close()


def _write(ws, filename: str, content: str) -> ActionExecution:
    """Runs the real document handler and records the execution like the executor does."""
    definition = ws.action_registry.get("files.create_document")
    ex = ActionExecution(id=f"exec-{uuid.uuid4().hex[:8]}", action_id="files.create_document", workspace_id=ws.id,
                         input_data={"filename": filename, "content": content})
    ex.output_data = ws.action_executor._execute_builtin_action(definition, ex)
    ex.status = ActionExecutionStatus.SUCCEEDED
    ws.action_store.save_execution(ex)
    return ex


def _file(ws, name: str) -> Path:
    return ws.action_executor._user_files_base(ws) / name


def _req() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/api/undo", "headers": [], "app": app})


def test_a_created_document_can_be_deleted_again_once(ws):
    ex = _write(ws, "report.md", "# v1")
    assert _file(ws, "report.md").read_text() == "# v1" and ex.output_data["sha256"]
    item = next(i for i in undo_mod.list_items(ws, ws.id) if i["execution_id"] == ex.id)
    assert item["reversible"] and item["kind"] == "delete"
    res = undo_mod.undo(ws, ex.id)
    assert res["result"] == "deleted" and not _file(ws, "report.md").exists()
    kept = Path(res["kept"])
    assert kept.read_text() == "# v1", "what the undo removed is still recoverable"
    with pytest.raises(undo_mod.UndoError) as e:
        undo_mod.undo(ws, ex.id)
    assert e.value.code == "already_undone"


def test_an_overwrite_is_restored_to_the_previous_version(ws):
    _write(ws, "notes.md", "first")
    second = _write(ws, "notes.md", "second")
    assert second.output_data["status"] == "updated"
    res = undo_mod.undo(ws, second.id)
    assert res["result"] == "restored" and _file(ws, "notes.md").read_text() == "first"
    assert Path(res["kept"]).read_text() == "second"


def test_undo_refuses_when_the_file_changed_after_aether_wrote_it(ws):
    ex = _write(ws, "plan.md", "by aether")
    _file(ws, "plan.md").write_text("by aether + my own edits")
    item = next(i for i in undo_mod.list_items(ws, ws.id) if i["execution_id"] == ex.id)
    assert not item["reversible"] and item["reason"] == "changed_since"
    with pytest.raises(undo_mod.UndoError) as e:
        undo_mod.undo(ws, ex.id)
    assert e.value.code == "changed_since" and _file(ws, "plan.md").read_text() == "by aether + my own edits"


def test_unknown_executions_and_other_actions_are_never_undoable(ws):
    with pytest.raises(undo_mod.UndoError) as e:
        undo_mod.undo(ws, "exec-nope")
    assert e.value.code == "not_found"
    other = ActionExecution(id="exec-other", action_id="calendar.create_event", workspace_id=ws.id, status=ActionExecutionStatus.SUCCEEDED)
    ws.action_store.save_execution(other)
    assert all(i["execution_id"] != "exec-other" for i in undo_mod.list_items(ws, ws.id)), "only reversible kinds are offered"
    with pytest.raises(undo_mod.UndoError) as e2:
        undo_mod.undo(ws, "exec-other")
    assert e2.value.code == "no_undo"


def test_http_surface(ws):
    ex = _write(ws, "http.md", "hello")
    items = asyncio.run(undo_list_route(_req()))["items"]
    assert any(i["execution_id"] == ex.id and i["reversible"] for i in items)
    assert asyncio.run(undo_apply_route(_req(), ex.id))["result"] == "deleted"
    with pytest.raises(HTTPException) as e:
        asyncio.run(undo_apply_route(_req(), ex.id))
    assert e.value.status_code == 409 and e.value.detail["code"] == "already_undone"
    with pytest.raises(HTTPException) as e2:
        asyncio.run(undo_apply_route(_req(), "exec-missing"))
    assert e2.value.status_code == 404
