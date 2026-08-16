"""
Tests for explicit Stop command ensuring final status is 'interrupted' and not 'completed'.
"""
import asyncio
import time
import json
import pytest
from fastapi import WebSocketDisconnect

from aether.workspace.workspace import Workspace
from aether.presets.applier import PresetApplier
from aether.server.app import app
from aether.server.sockets import websocket_endpoint
from aether.core.execution import ExecutionResult


class MockControllableWebSocket:
    def __init__(self, app_instance):
        self.app = app_instance
        self.queue = asyncio.Queue()
        self.sent = []
        self.closed = False

    async def accept(self):
        pass

    async def send_json(self, data):
        self.sent.append(data)

    async def receive_text(self):
        msg = await self.queue.get()
        if msg is None:
            raise WebSocketDisconnect(code=1000)
        return msg

    async def push_msg(self, msg: str):
        await self.queue.put(msg)

    async def disconnect(self):
        await self.queue.put(None)

    async def close(self, code=1000):
        self.closed = True


@pytest.mark.asyncio
async def test_explicit_stop_sets_status_interrupted(tmp_path, monkeypatch):
    """When user stops task, final status is 'interrupted' and activity records interrupted."""
    ws_dir = tmp_path / "stop-ws"
    ws = Workspace.init(ws_dir, name="Stop Test Workspace")
    PresetApplier().apply_preset("starter-workforce", ws)

    app.state.workspace = ws
    app.state.workspace_root = ws.root
    team = ws.load_team()
    app.state.team = team
    app.state.active_team_name = "default"
    app.state.active_tasks = {}
    app.state.chat_sockets = set()
    app.state.hitl_queues = {}

    def slow_run(prompt, session_id):
        # Simulate long running task
        for _ in range(50):
            time.sleep(0.05)
        return ExecutionResult(output="Should not complete", success=True)

    monkeypatch.setattr(team, "run", slow_run)

    session_id = "conv_stop_test_999"
    mock_ws = MockControllableWebSocket(app)

    # Start WebSocket handler task
    ws_task = asyncio.create_task(websocket_endpoint(mock_ws))

    # Send run_task
    await mock_ws.push_msg(json.dumps({
        "type": "run_task",
        "content": "Perform long analysis",
        "session_id": session_id
    }))
    await asyncio.sleep(0.1)

    # Verify task is running
    assert session_id in app.state.active_tasks
    assert not app.state.active_tasks[session_id].done()

    # Send explicit stop
    await mock_ws.push_msg(json.dumps({
        "type": "stop",
        "session_id": session_id
    }))
    await asyncio.sleep(0.2)

    # Verify task was stopped
    conv = ws.conversations.get(session_id)
    assert conv is not None
    assert conv["status"] == "interrupted"
    assert conv["status"] != "completed"

    # Verify activity was recorded as interrupted
    activities = conv.get("activities", [])
    interrupted_acts = [a for a in activities if a["type"] == "task_interrupted"]
    assert len(interrupted_acts) > 0

    await mock_ws.disconnect()
    await ws_task
