"""
Tests for Macro-Step 19: Aether Companion & Universal Interaction (Phase D).
Verifies desktop app context capture, deliverables collector, drag & drop ingestion,
quick actions, Telegram operational bridge alignment, and FastAPI endpoints.
"""
from __future__ import annotations

import base64
from pathlib import Path
import tempfile
from typing import Any
from unittest.mock import patch

import pytest
from starlette.requests import Request

from aether.actions.models import ActionExecutionStatus
from aether.connections.models import Connection, ConnectionStatus
from aether.connections.telegram_bridge import TelegramBridge
from aether.personal.context import (
    capture_desktop_context,
    collect_workspace_deliverables,
    handle_drag_and_drop_file,
)
from aether.personal.models import (
    CompanionDeliverable,
    DesktopAppContext,
)
from aether.server.routes import (
    CompanionDropPayload,
    CompanionQuickActionPayload,
    companion_drop_route,
    execute_companion_quick_action_route,
    get_companion_context_route,
    list_companion_deliverables_route,
)
from aether.workspace.workspace import Workspace


@pytest.fixture
def temp_workspace(tmp_path: Path):
    ws_dir = tmp_path / "test_companion_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return Workspace(root=ws_dir)


class DummyAppState:
    def __init__(self, workspace: Any) -> None:
        self.workspace = workspace


class DummyApp:
    def __init__(self, workspace: Any) -> None:
        self.state = DummyAppState(workspace)


def create_dummy_request(workspace: Any, body: dict[str, Any] | None = None) -> Request:
    scope = {"type": "http", "app": DummyApp(workspace), "headers": []}
    req = Request(scope=scope)
    if body is not None:
        async def fake_json():
            return body
        req.json = fake_json  # type: ignore[method-assign]
    return req


def test_desktop_context_probing_zero_simulation():
    """Verifies native desktop context probing with truthful platform inspection."""
    ctx = capture_desktop_context(timeout_seconds=1.0)
    assert isinstance(ctx, DesktopAppContext)
    assert len(ctx.app_name) > 0
    assert ctx.timestamp is not None

    d = ctx.to_dict()
    assert "app_name" in d
    assert "clipboard_text" in d
    assert "screen_summary" in d

    rev = DesktopAppContext.from_dict(d)
    assert rev.app_name == ctx.app_name


def test_collect_workspace_deliverables(temp_workspace: Workspace):
    """Verifies deliverable collection across missions, tasks, and inbox directories."""
    ws = temp_workspace
    ws_id = ws.name

    # Create dummy deliverable files in deliverables folder
    deliv_dir = ws.root / "deliverables"
    deliv_dir.mkdir(parents=True, exist_ok=True)
    sample_file = deliv_dir / "Q3_Financial_Analysis.pdf"
    sample_file.write_text("dummy pdf binary content")

    inbox_dir = ws.root / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    sample_doc = inbox_dir / "Architecture_Blueprint.md"
    sample_doc.write_text("# Aether Architecture\nLayered design.")

    deliverables = collect_workspace_deliverables(ws, limit=10)
    assert len(deliverables) >= 2
    titles = [d.title for d in deliverables]
    assert "Q3_Financial_Analysis.pdf" in titles or "Architecture_Blueprint.md" in titles


def test_drag_and_drop_file_ingestion(temp_workspace: Workspace):
    """Verifies file ingestion into workspace inbox via drag & drop."""
    ws = temp_workspace
    content = b"# Sales Report\nTotal Revenue: $450,000\nProfit Margin: 32%"

    res = handle_drag_and_drop_file(
        workspace=ws,
        filename="Q4_Sales_Report.md",
        content=content,
        session_id="test-session-1",
    )
    assert res["status"] == "ingested"
    assert res["file_name"].startswith("Q4_Sales_Report")
    assert res["file_size"] == len(content)
    assert "Sales Report" in res["text_preview"]

    inbox_file = Path(res["file_path"])
    assert inbox_file.exists()
    assert inbox_file.read_bytes() == content


def test_companion_quick_actions(temp_workspace: Workspace):
    """Verifies instant companion quick action execution."""
    ws = temp_workspace
    ws_id = ws.name

    # 1. Quick action: capture screen context
    res_ctx = ws.personal.execute_quick_action(ws_id, "capture_screen_context")
    assert res_ctx["action"] == "capture_screen_context"
    assert res_ctx["status"] == "completed"
    assert "context" in res_ctx

    # 2. Quick action: check notifications
    res_notif = ws.personal.execute_quick_action(ws_id, "check_notifications")
    assert res_notif["action"] == "check_notifications"
    assert "unread_count" in res_notif

    # 3. Quick action: mesh audit
    res_audit = ws.personal.execute_quick_action(ws_id, "run_quick_audit")
    assert res_audit["action"] == "run_quick_audit"
    assert "telemetry" in res_audit

    # 4. Quick action: refresh deliverables
    res_deliv = ws.personal.execute_quick_action(ws_id, "refresh_deliverables")
    assert res_deliv["action"] == "refresh_deliverables"
    assert "deliverables" in res_deliv


def test_telegram_bridge_operational_alignment(temp_workspace: Workspace):
    """Verifies Telegram bridge supports /status, /missions, and /deliverables commands."""
    ws = temp_workspace
    ws_id = ws.name

    # Configure Telegram connection
    conn = Connection(
        id=f"conn-tg-{ws_id}",
        workspace_id=ws_id,
        provider="telegram",
        account_name="Telegram Bot",
        status=ConnectionStatus.CONNECTED,
        auth_metadata={"bot_token": "dummy_test_token", "authorized_chats": [12345]},
    )
    ws.connections.save_connection(conn)

    # 1. /status command
    with patch("aether.connections.telegram.TelegramConnector.send_message") as mock_send:
        mock_send.return_value = {"ok": True}
        update_status = {
            "message": {
                "chat": {"id": 12345},
                "text": "/status",
            }
        }
        res_status = TelegramBridge.handle_update(update_status, ws)
        assert res_status["status"] == "status_sent"
        assert mock_send.called
        assert "Stato Operativo Aether" in mock_send.call_args[1]["text"]

        # 2. /missions command
        update_missions = {
            "message": {
                "chat": {"id": 12345},
                "text": "/missions",
            }
        }
        res_missions = TelegramBridge.handle_update(update_missions, ws)
        assert res_missions["status"] == "missions_sent"
        assert "missione" in mock_send.call_args[1]["text"].lower()

        # 3. /deliverables command
        update_delivs = {
            "message": {
                "chat": {"id": 12345},
                "text": "/deliverables",
            }
        }
        res_delivs = TelegramBridge.handle_update(update_delivs, ws)
        assert res_delivs["status"] == "deliverables_sent"
        assert "deliverable" in mock_send.call_args[1]["text"].lower()


@pytest.mark.asyncio
async def test_fastapi_companion_routes(temp_workspace: Workspace):
    """Verifies REST endpoints for companion context, deliverables, drop, and quick actions."""
    ws = temp_workspace
    ws_id = ws.name

    # 1. Capture context endpoint
    req_ctx = create_dummy_request(ws)
    ctx_res = await get_companion_context_route(req_ctx)
    assert "app_name" in ctx_res
    assert "timestamp" in ctx_res

    # 2. Drag & Drop file ingestion endpoint
    req_drop = create_dummy_request(ws)
    file_bytes = b"import sys\nprint('Companion Test')\n"
    b64_content = base64.b64decode(base64.b64encode(file_bytes)).decode("utf-8")
    payload_drop = CompanionDropPayload(
        filename="test_companion_script.py",
        text_content=b64_content,
        workspace_id=ws_id,
    )
    drop_res = await companion_drop_route(req_drop, payload_drop)
    assert drop_res["status"] == "ingested"
    assert "test_companion_script" in drop_res["file_name"]

    # 3. List deliverables endpoint
    req_deliv = create_dummy_request(ws)
    delivs = await list_companion_deliverables_route(req_deliv, workspace_id=ws_id)
    assert isinstance(delivs, list)
    assert len(delivs) >= 1

    # 4. Quick Action endpoint
    req_qa = create_dummy_request(ws)
    qa_payload = CompanionQuickActionPayload(
        action_id="capture_screen_context",
        workspace_id=ws_id,
    )
    qa_res = await execute_companion_quick_action_route(req_qa, qa_payload)
    assert qa_res["action"] == "capture_screen_context"
    assert qa_res["status"] == "completed"
