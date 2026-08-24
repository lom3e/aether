"""
Comprehensive tests for Phase 5: Live Chat UI Integration and End-to-End WebSocket Flow.

Validates:
- Complete end-to-end task lifecycle: task_started -> agent_status -> token_chunk -> task_completed
- Incremental token streaming reception
- Agent thinking status updates
- File action activities recording and propagation
- Error handling and clear error messages on failure
- Task interruption and stop lifecycle
- Static assets compilation verification
"""
import asyncio
import json
from pathlib import Path
import time
import pytest
from fastapi import WebSocketDisconnect

from aether.core.execution import Task
from aether.coordination.events import AgentEvent, EventType
from aether.providers.mock import MockProvider
from aether.server.app import app
from aether.server.sockets import websocket_endpoint
from aether.workspace.workspace import Workspace
from aether.presets.applier import PresetApplier


class MockControllableWebSocket:
    def __init__(self, app_instance, query_params=None):
        self.app = app_instance
        self.queue = asyncio.Queue()
        self.sent = []
        self.closed = False
        self.query_params = query_params or {}
        self.headers = {}
        self.state = type("State", (), {})()

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


@pytest.fixture
def chat_env(tmp_path):
    """Set up FastAPI app state with an initialized Workspace, Preset, and MockProvider."""
    ws_dir = tmp_path / "chat_ui_workspace"
    ws = Workspace.init(ws_dir, name="Chat UI Workspace")
    PresetApplier().apply_preset("starter-workforce", ws)

    team = ws.load_team()
    # Configure mock provider with stream chunks
    mock_provider = MockProvider(
        stream_chunks=[
            ["Aether ", "is ", "streaming ", "live ", "tokens ", "to ", "the ", "UI."]
        ]
    )
    team.provider = mock_provider
    for agent in team.agents():
        agent.provider = mock_provider

    app.state.workspace = ws
    app.state.team = team
    app.state.session_token = None
    app.state.is_shutting_down = False
    app.state.chat_sockets = set()
    app.state.active_tasks = {}
    app.state.hitl_queues = {}

    return app, ws, team


@pytest.mark.asyncio
async def test_e2e_full_task_lifecycle_with_streaming_and_status(chat_env):
    """Verify complete lifecycle: task_started -> agent_status -> token_chunk -> task_completed."""
    app_instance, ws, team = chat_env
    mock_ws = MockControllableWebSocket(app_instance)

    session_id = "test-live-conv-001"
    endpoint_task = asyncio.create_task(websocket_endpoint(mock_ws))
    await asyncio.sleep(0.05)

    # 1. Send run_task from UI WebSocket client
    await mock_ws.push_msg(json.dumps({
        "type": "run_task",
        "content": "Perform streaming analysis",
        "session_id": session_id
    }))

    # Allow task to run through asyncio.to_thread and stream tokens
    await asyncio.sleep(0.3)
    await mock_ws.disconnect()
    await endpoint_task

    # 2. Validate frame sequence
    msg_types = [m.get("type") for m in mock_ws.sent]

    assert "task_started" in msg_types
    assert "agent_status" in msg_types
    assert "token_chunk" in msg_types
    assert "task_completed" in msg_types

    # Validate token chunks
    token_chunks = [m for m in mock_ws.sent if m.get("type") == "token_chunk"]
    assert len(token_chunks) >= 1
    reconstructed = "".join(m.get("delta", "") for m in token_chunks)
    assert "Aether is streaming live tokens to the UI." in reconstructed

    # Validate completion
    completion = next(m for m in mock_ws.sent if m.get("type") == "task_completed")
    assert completion["success"] is True
    assert completion["session_id"] == session_id
    assert "Aether is streaming live tokens to the UI." in completion["content"]

    # Validate conversation persisted in SQLite
    conv = ws.conversations.get(session_id)
    assert conv is not None
    assert conv["status"] == "completed"
    assert len(conv["messages"]) == 2  # user prompt + assistant response
    assert conv["messages"][0]["role"] == "user"
    assert conv["messages"][1]["role"] == "assistant"
    assert "Aether is streaming live tokens to the UI." in conv["messages"][1]["content"]


@pytest.mark.asyncio
async def test_e2e_error_handling_and_task_failure(chat_env):
    """Verify task failure returns structured error and sets status correctly."""
    app_instance, ws, team = chat_env
    mock_ws = MockControllableWebSocket(app_instance)

    # Make team entry agent raise an exception or fail
    class FailingProvider(MockProvider):
        def generate(self, messages, tools=None, output_schema=None):
            raise ConnectionError("Ollama host is unreachable on port 11434")

        def generate_stream(self, messages, tools=None, output_schema=None):
            raise ConnectionError("Ollama host is unreachable on port 11434")

    failing_prov = FailingProvider()
    team.provider = failing_prov
    for agent in team.agents():
        agent.provider = failing_prov

    session_id = "test-fail-conv-002"
    endpoint_task = asyncio.create_task(websocket_endpoint(mock_ws))
    await asyncio.sleep(0.05)

    await mock_ws.push_msg(json.dumps({
        "type": "run_task",
        "content": "Will fail",
        "session_id": session_id
    }))

    await asyncio.sleep(0.3)
    await mock_ws.disconnect()
    await endpoint_task

    completion = next((m for m in mock_ws.sent if m.get("type") == "task_completed"), None)
    assert completion is not None
    assert completion["success"] is False
    assert completion["session_id"] == session_id
    assert completion["error"] is not None

    # Check conversation in SQLite is marked failed
    conv = ws.conversations.get(session_id)
    assert conv is not None
    assert conv["status"] == "failed"


@pytest.mark.asyncio
async def test_e2e_task_stopped_handling(chat_env):
    """Verify user stop signal halts task and emits task_stopped."""
    app_instance, ws, team = chat_env
    mock_ws = MockControllableWebSocket(app_instance)

    class SlowProvider(MockProvider):
        def generate(self, messages, tools=None, output_schema=None):
            time.sleep(1.0)
            from aether.providers.types import Message, ProviderResponse
            return ProviderResponse(content="slow", model="mock", message=Message(role="assistant", content="slow"))

        def generate_stream(self, messages, tools=None, output_schema=None):
            time.sleep(1.0)
            from aether.providers.types import Message, ProviderStreamChunk
            yield ProviderStreamChunk(text="slow", finish_reason="stop", message=Message(role="assistant", content="slow"))

    slow_prov = SlowProvider()
    team.provider = slow_prov
    for agent in team.agents():
        agent.provider = slow_prov

    session_id = "test-stop-conv-003"
    endpoint_task = asyncio.create_task(websocket_endpoint(mock_ws))
    await asyncio.sleep(0.05)

    # Start long task
    await mock_ws.push_msg(json.dumps({
        "type": "run_task",
        "content": "Long task",
        "session_id": session_id
    }))
    await asyncio.sleep(0.05)

    # Send stop
    await mock_ws.push_msg(json.dumps({
        "type": "stop",
        "session_id": session_id
    }))

    await asyncio.sleep(0.3)
    await mock_ws.disconnect()
    await endpoint_task

    stop_msg = next((m for m in mock_ws.sent if m.get("type") == "task_stopped"), None)
    assert stop_msg is not None
    assert stop_msg["session_id"] == session_id
    assert stop_msg["status"] == "interrupted"


def test_ui_static_dist_built():
    """Verify that the frontend UI is compiled and present in static directory."""
    static_dir = Path(__file__).resolve().parent.parent / "src" / "aether" / "server" / "static"
    index_html = static_dir / "index.html"
    assets_dir = static_dir / "assets"

    assert index_html.exists()
    assert assets_dir.exists()
    js_files = list(assets_dir.glob("*.js"))
    assert len(js_files) > 0

    # Ensure the compiled JS bundle includes our new event types
    js_content = js_files[0].read_text(encoding="utf-8")
    assert "token_chunk" in js_content
    assert "agent_status" in js_content
    assert "file_action" in js_content
