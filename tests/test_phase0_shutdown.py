"""
Tests for PRE-02: Graceful Shutdown (/api/system/shutdown).
"""
import asyncio
import pytest
from starlette.requests import Request
from aether.server.app import app
from aether.server.routes import system_shutdown
from aether.workspace.workspace import Workspace
from aether.presets.applier import PresetApplier


def make_shutdown_request():
    scope = {"type": "http", "app": app, "headers": [], "path": "/api/system/shutdown", "method": "POST"}
    return Request(scope)


@pytest.mark.asyncio
async def test_shutdown_endpoint_idle():
    """Shutdown endpoint responds with shutting_down when server is idle."""
    app.state.active_tasks = {}
    app.state.is_shutting_down = False

    req = make_shutdown_request()
    data = await system_shutdown(req)
    assert data["status"] == "shutting_down"
    assert app.state.is_shutting_down is True


@pytest.mark.asyncio
async def test_shutdown_endpoint_repeated_calls():
    """Repeated shutdown requests are idempotent."""
    app.state.active_tasks = {}
    app.state.is_shutting_down = False

    req = make_shutdown_request()
    r1 = await system_shutdown(req)
    r2 = await system_shutdown(req)
    assert r1["status"] == "shutting_down"
    assert r2["status"] == "shutting_down"


@pytest.mark.asyncio
async def test_shutdown_cancels_active_tasks_gracefully(tmp_path):
    """Shutdown endpoint cancels running asyncio tasks cleanly."""
    ws_dir = tmp_path / "shutdown-active-ws"
    ws = Workspace.init(ws_dir, name="Shutdown Active Workspace")
    PresetApplier().apply_preset("starter-workforce", ws)

    app.state.workspace = ws
    app.state.workspace_root = ws.root
    app.state.is_shutting_down = False

    async def long_task():
        await asyncio.sleep(10.0)

    task = asyncio.create_task(long_task())
    # Yield control to let long_task start running
    await asyncio.sleep(0.01)

    app.state.active_tasks = {"test_session_123": task}

    req = make_shutdown_request()
    data = await system_shutdown(req)
    assert data["status"] == "shutting_down"
    assert data["active_tasks_cancelled"] == 1

    # Await task cancellation
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert task.cancelled() is True
