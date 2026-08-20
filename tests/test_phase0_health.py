"""
Tests for PRE-01: Fast, workspace-independent Health Check endpoint (/api/health).
"""
import pytest
from starlette.requests import Request
from aether.server.app import app
from aether.server.routes import health
from aether import __version__


def make_request():
    scope = {"type": "http", "app": app, "headers": [], "path": "/api/health", "method": "GET"}
    return Request(scope)


@pytest.mark.asyncio
async def test_health_endpoint_no_workspace():
    """Health endpoint responds 200 OK even when no workspace is initialized."""
    app.state.workspace = None
    app.state.workspace_root = None
    app.state.team = None
    app.state.active_team_name = None

    req = make_request()
    data = await health(req)
    assert data["status"] == "ok"
    assert data["version"] == __version__
    assert data["workspace_initialized"] is False
    assert data["workspace_root"] is None


@pytest.mark.asyncio
async def test_health_endpoint_with_active_workspace(tmp_path):
    """Health endpoint accurately reports active workspace details."""
    from aether.workspace.workspace import Workspace
    ws_dir = tmp_path / "test-health-ws"
    ws = Workspace.init(ws_dir, name="Health Workspace")

    app.state.workspace = ws
    app.state.workspace_root = ws.root

    req = make_request()
    data = await health(req)
    assert data["status"] == "ok"
    assert data["version"] == __version__
    assert data["workspace_initialized"] is True
    assert data["workspace_root"] == str(ws.root.resolve())
