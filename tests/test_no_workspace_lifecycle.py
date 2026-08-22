"""
Regression and lifecycle tests for the explicit 'No Active Workspace' state and operations.

Covers:
- Case A: 0 workspaces registered -> GET /api/workspace returns active = null (name="")
- Case B: 0 workspaces -> GET /api/workspace/home, /api/workspaces, POST /api/conversations safe error handling
- Case C: 0 workspaces -> WebSocket /ws/chat rejects cleanly without unhandled exception
- Case D: Workspace A -> Delete Workspace A -> 0 workspaces -> active becomes None cleanly
- Case E: 0 workspaces -> startup resolution keeps activeWorkspace = None
- Case F: Create workspace -> transitions to active workspace smoothly
"""
import pytest
import asyncio
from pathlib import Path
from starlette.requests import Request
from fastapi import HTTPException

from aether.workspace.workspace import Workspace
from aether.workspace.registry import WorkspaceRegistry
from aether.server.app import app, startup_event
from aether.server.routes import (
    get_workspace,
    get_workspace_home,
    list_all_workspaces,
    create_conversation,
    create_new_workspace,
    delete_workspace_endpoint,
    CreateWorkspacePayload,
    CreateConversationPayload,
)
from aether.server.sockets import websocket_endpoint


def mock_request():
    scope = {"type": "http", "app": app, "headers": []}
    return Request(scope)


class MockWS:
    def __init__(self, app_instance):
        self.app = app_instance
        self.sent = []
        self.closed = False
        self.close_code = None

    async def accept(self):
        pass

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self, code=1000):
        self.closed = True
        self.close_code = code


@pytest.fixture
def clean_registry(tmp_path, monkeypatch):
    reg_file = tmp_path / "workspaces.json"
    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr("aether.workspace.registry._get_registry_path", lambda: reg_file)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.mark.asyncio
async def test_case_a_and_b_zero_workspaces_api_responses(clean_registry):
    """Case A & B: When 0 workspaces exist, API endpoints respond cleanly without 500 errors."""
    app.state.workspace = None
    app.state.workspace_root = None
    app.state.team = None
    app.state.active_team_name = None

    req = mock_request()

    # 1. GET /api/workspace
    ws_info = await get_workspace(req)
    assert ws_info.name == ""
    assert ws_info.has_default_team is False
    assert ws_info.agents == []
    assert ws_info.knowledge_chunks == 0

    # 2. GET /api/workspace/home
    home_data = await get_workspace_home(req)
    assert home_data["workspace_name"] == ""
    assert home_data["agent_count"] == 0

    # 3. GET /api/workspaces
    ws_list = await list_all_workspaces(req)
    assert ws_list == []

    # 4. POST /api/conversations should return 400 (not 500)
    with pytest.raises(HTTPException) as exc_info:
        await create_conversation(req, CreateConversationPayload(title="Test Conv"))
    assert exc_info.value.status_code == 400
    assert "No active workspace" in exc_info.value.detail


@pytest.mark.asyncio
async def test_case_c_websocket_rejection_when_no_workspace(clean_registry):
    """Case C: Connecting to WebSocket when no workspace exists closes cleanly with error message."""
    app.state.workspace = None
    app.state.workspace_root = None
    app.state.team = None
    app.state.active_team_name = None

    mock_ws = MockWS(app)
    await websocket_endpoint(mock_ws)

    assert mock_ws.closed is True
    assert mock_ws.close_code == 1011
    assert len(mock_ws.sent) == 1
    assert mock_ws.sent[0]["type"] == "error"
    assert "not initialized" in mock_ws.sent[0]["message"].lower()


@pytest.mark.asyncio
async def test_case_d_delete_last_workspace_transitions_to_no_workspace_state(clean_registry, tmp_path):
    """Case D: Deleting the last active workspace resets app state to None with 0 residual items."""
    ws_dir = tmp_path / "ws-alpha"
    ws = WorkspaceRegistry.create_workspace(
        name="Workspace Alpha",
        preset_id="empty",
        target_dir=ws_dir
    )
    app.state.workspace = ws
    app.state.workspace_root = ws.root
    app.state.team = ws.load_team()

    req = mock_request()

    # Verify active
    info = await get_workspace(req)
    assert info.name == "Workspace Alpha"

    # Delete workspace
    entry = WorkspaceRegistry.get_workspace_entry(ws.root)
    assert entry is not None
    del_res = await delete_workspace_endpoint(req, entry["id"])
    assert del_res == {"status": "ok"}

    # Verify state transitioned to None
    assert app.state.workspace is None
    assert app.state.workspace_root is None
    assert app.state.team is None

    # Verify subsequent GET /api/workspace
    res_after = await get_workspace(req)
    assert res_after.name == ""

    # Verify list is empty
    assert await list_all_workspaces(req) == []


@pytest.mark.asyncio
async def test_case_e_startup_resolution_with_zero_workspaces(clean_registry, monkeypatch):
    """Case E: Server startup with 0 registered workspaces leaves workspace as None."""
    monkeypatch.delenv("AETHER_WORKSPACE", raising=False)
    monkeypatch.setattr(Path, "cwd", lambda: clean_registry / "empty-cwd")

    app.state.workspace = "stale"
    app.state.workspace_root = "stale"
    app.state.team = "stale"

    await startup_event()

    assert app.state.workspace is None
    assert app.state.workspace_root is None
    assert app.state.team is None


@pytest.mark.asyncio
async def test_case_f_create_workspace_transitions_smoothly(clean_registry, tmp_path):
    """Case F: Creating a workspace when 0 exist immediately makes it the active workspace."""
    app.state.workspace = None
    app.state.workspace_root = None
    app.state.team = None

    req = mock_request()
    res = await create_new_workspace(req, CreateWorkspacePayload(
        name="First New Workspace",
        preset_id="starter-workforce"
    ))
    assert res["status"] == "ok"

    assert app.state.workspace is not None
    assert app.state.workspace.config["workspace"]["name"] == "First New Workspace"
    assert app.state.team is not None

    res_ws = await get_workspace(req)
    assert res_ws.name == "First New Workspace"
    assert res_ws.has_default_team is True


@pytest.mark.asyncio
async def test_case_g_delete_active_workspace_switches_to_remaining(clean_registry, tmp_path):
    """Case G: Deleting the active workspace when another exists switches active to remaining."""
    ws_a = WorkspaceRegistry.create_workspace(
        name="Workspace Alpha",
        preset_id="empty",
        target_dir=tmp_path / "ws-alpha"
    )
    ws_b = WorkspaceRegistry.create_workspace(
        name="Workspace Beta",
        preset_id="empty",
        target_dir=tmp_path / "ws-beta"
    )

    app.state.workspace = ws_a
    app.state.workspace_root = ws_a.root
    app.state.team = ws_a.load_team()

    req = mock_request()

    # Delete active workspace (Alpha)
    entry_a = WorkspaceRegistry.get_workspace_entry(ws_a.root)
    del_res = await delete_workspace_endpoint(req, entry_a["id"])
    assert del_res == {"status": "ok"}

    # Alpha directory should no longer exist
    assert not (tmp_path / "ws-alpha").exists()

    # Active workspace should have automatically switched to Beta
    assert app.state.workspace is not None
    assert app.state.workspace.root == ws_b.root
    assert app.state.workspace.config["workspace"]["name"] == "Workspace Beta"

    # Subsequent GET /api/workspace reflects Beta
    info = await get_workspace(req)
    assert info.name == "Workspace Beta"

    # Workspaces list contains only Beta and marks it active
    ws_list = await list_all_workspaces(req)
    assert len(ws_list) == 1
    assert ws_list[0]["name"] == "Workspace Beta"
    assert ws_list[0]["is_active"] is True


@pytest.mark.asyncio
async def test_case_h_delete_inactive_workspace_keeps_active(clean_registry, tmp_path):
    """Case H: Deleting an inactive workspace does not change active workspace."""
    ws_a = WorkspaceRegistry.create_workspace(
        name="Workspace Alpha",
        preset_id="empty",
        target_dir=tmp_path / "ws-alpha"
    )
    ws_b = WorkspaceRegistry.create_workspace(
        name="Workspace Beta",
        preset_id="empty",
        target_dir=tmp_path / "ws-beta"
    )

    app.state.workspace = ws_a
    app.state.workspace_root = ws_a.root
    app.state.team = ws_a.load_team()

    req = mock_request()

    # Delete inactive workspace (Beta)
    entry_b = WorkspaceRegistry.get_workspace_entry(ws_b.root)
    del_res = await delete_workspace_endpoint(req, entry_b["id"])
    assert del_res == {"status": "ok"}

    # Beta directory should no longer exist
    assert not (tmp_path / "ws-beta").exists()

    # Active workspace remains Alpha
    assert app.state.workspace is not None
    assert app.state.workspace.root == ws_a.root

    info = await get_workspace(req)
    assert info.name == "Workspace Alpha"


@pytest.mark.asyncio
async def test_case_i_delete_nonexistent_workspace_returns_404(clean_registry):
    """Case I: Attempting to delete a non-existent workspace ID returns 404."""
    req = mock_request()
    with pytest.raises(HTTPException) as exc_info:
        await delete_workspace_endpoint(req, "non-existent-ws-id")
    assert exc_info.value.status_code == 404
