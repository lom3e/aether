"""
Comprehensive tests for Phase 4: Live WebSocket Event Bridge.

Validates:
- Real-time token streaming chunks forwarding (`token_chunk`)
- Agent status updates (`agent_status`)
- Filesystem actions forwarding (`file_action`)
- Session isolation across multiple WebSocket connections
- Cross-thread safety and non-blocking background emission
- Client disconnection and closed-connection resilience
- Session joining and lifecycle handling
"""
import asyncio
import json
import threading
import pytest
from fastapi import WebSocketDisconnect

from aether.coordination.events import AgentEvent, EventType, EventEmitter
from aether.server.app import app
from aether.server.sockets import websocket_endpoint
from aether.workspace.workspace import Workspace
from aether.presets.applier import PresetApplier


class MockControllableWebSocket:
    def __init__(self, app_instance, query_params=None, fail_on_send=False):
        self.app = app_instance
        self.queue = asyncio.Queue()
        self.sent = []
        self.closed = False
        self.query_params = query_params or {}
        self.headers = {}
        self.fail_on_send = fail_on_send
        self.state = type("State", (), {})()

    async def accept(self):
        pass

    async def send_json(self, data):
        if self.fail_on_send:
            raise ConnectionResetError("Client connection abruptly closed.")
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
def ws_app_env(tmp_path):
    """Set up FastAPI app state with an initialized Workspace and Team."""
    ws_dir = tmp_path / "live_ws_workspace"
    ws = Workspace.init(ws_dir, name="Live WS Workspace")
    PresetApplier().apply_preset("starter-workforce", ws)

    app.state.workspace = ws
    app.state.team = ws.load_team()
    app.state.session_token = None
    app.state.is_shutting_down = False
    app.state.chat_sockets = set()
    app.state.active_tasks = {}
    app.state.hitl_queues = {}

    return app, ws, app.state.team


# ---------------------------------------------------------------------------
# 1. Real-time Event Bridge Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ws_token_stream_event_forwarding(ws_app_env):
    app_instance, ws, team = ws_app_env
    mock_ws = MockControllableWebSocket(app_instance)

    endpoint_task = asyncio.create_task(websocket_endpoint(mock_ws))
    await asyncio.sleep(0.05)

    # Emit a token stream chunk from agent/team emitter
    team.emitter.emit(
        AgentEvent(
            event_type=EventType.TOKEN_STREAM,
            agent_name="code-analyst",
            task_id="conv-100",
            metadata={"delta": "def solve():\n"},
        )
    )

    await asyncio.sleep(0.05)
    await mock_ws.disconnect()
    await endpoint_task

    token_messages = [msg for msg in mock_ws.sent if msg.get("type") == "token_chunk"]
    assert len(token_messages) == 1
    assert token_messages[0]["type"] == "token_chunk"
    assert token_messages[0]["session_id"] == "conv-100"
    assert token_messages[0]["agent"] == "code-analyst"
    assert token_messages[0]["delta"] == "def solve():\n"


@pytest.mark.asyncio
async def test_ws_agent_thinking_status_forwarding(ws_app_env):
    app_instance, ws, team = ws_app_env
    mock_ws = MockControllableWebSocket(app_instance)

    endpoint_task = asyncio.create_task(websocket_endpoint(mock_ws))
    await asyncio.sleep(0.05)

    # Emit thinking status event
    team.emitter.emit(
        AgentEvent(
            event_type=EventType.AGENT_THINKING,
            agent_name="researcher",
            task_id="conv-101",
            metadata={"status": "thinking"},
        )
    )

    await asyncio.sleep(0.05)
    await mock_ws.disconnect()
    await endpoint_task

    status_messages = [msg for msg in mock_ws.sent if msg.get("type") == "agent_status"]
    assert len(status_messages) == 1
    assert status_messages[0]["type"] == "agent_status"
    assert status_messages[0]["session_id"] == "conv-101"
    assert status_messages[0]["agent"] == "researcher"
    assert status_messages[0]["status"] == "thinking"


@pytest.mark.asyncio
async def test_ws_file_action_events_forwarding(ws_app_env):
    app_instance, ws, team = ws_app_env
    mock_ws = MockControllableWebSocket(app_instance)

    endpoint_task = asyncio.create_task(websocket_endpoint(mock_ws))
    await asyncio.sleep(0.05)

    # 1. FILE_CREATED
    team.emitter.emit(
        AgentEvent(
            event_type=EventType.FILE_CREATED,
            agent_name="code-analyst",
            task_id="conv-102",
            metadata={"path": "src/api.py", "size_bytes": 256, "action": "created"},
        )
    )

    # 2. FILE_MODIFIED
    team.emitter.emit(
        AgentEvent(
            event_type=EventType.FILE_MODIFIED,
            agent_name="code-analyst",
            task_id="conv-102",
            metadata={"path": "src/api.py", "action": "patched"},
        )
    )

    # 3. FILE_DELETED
    team.emitter.emit(
        AgentEvent(
            event_type=EventType.FILE_DELETED,
            agent_name="code-analyst",
            task_id="conv-102",
            metadata={"path": "temp.log"},
        )
    )

    await asyncio.sleep(0.05)
    await mock_ws.disconnect()
    await endpoint_task

    file_messages = [msg for msg in mock_ws.sent if msg.get("type") == "file_action"]
    assert len(file_messages) == 3

    assert file_messages[0]["action"] == "created"
    assert file_messages[0]["path"] == "src/api.py"
    assert file_messages[0]["session_id"] == "conv-102"

    assert file_messages[1]["action"] == "modified"
    assert file_messages[1]["path"] == "src/api.py"

    assert file_messages[2]["action"] == "deleted"
    assert file_messages[2]["path"] == "temp.log"


# ---------------------------------------------------------------------------
# 2. Session Isolation Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ws_session_isolation(ws_app_env):
    app_instance, ws, team = ws_app_env

    # WS 1 bound to session-A
    ws1 = MockControllableWebSocket(app_instance, query_params={"session_id": "session-A"})
    # WS 2 bound to session-B
    ws2 = MockControllableWebSocket(app_instance, query_params={"session_id": "session-B"})

    t1 = asyncio.create_task(websocket_endpoint(ws1))
    t2 = asyncio.create_task(websocket_endpoint(ws2))
    await asyncio.sleep(0.05)

    # Emit event for session-A
    team.emitter.emit(
        AgentEvent(
            event_type=EventType.TOKEN_STREAM,
            agent_name="agent-a",
            task_id="session-A",
            metadata={"delta": "Token A"},
        )
    )

    # Emit event for session-B
    team.emitter.emit(
        AgentEvent(
            event_type=EventType.TOKEN_STREAM,
            agent_name="agent-b",
            task_id="session-B",
            metadata={"delta": "Token B"},
        )
    )

    await asyncio.sleep(0.05)
    await ws1.disconnect()
    await ws2.disconnect()
    await t1
    await t2

    ws1_tokens = [m for m in ws1.sent if m.get("type") == "token_chunk"]
    ws2_tokens = [m for m in ws2.sent if m.get("type") == "token_chunk"]

    # WS1 only receives Token A
    assert len(ws1_tokens) == 1
    assert ws1_tokens[0]["delta"] == "Token A"
    assert ws1_tokens[0]["session_id"] == "session-A"

    # WS2 only receives Token B
    assert len(ws2_tokens) == 1
    assert ws2_tokens[0]["delta"] == "Token B"
    assert ws2_tokens[0]["session_id"] == "session-B"


# ---------------------------------------------------------------------------
# 3. Thread Safety & Background Emission Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ws_background_thread_emission(ws_app_env):
    app_instance, ws, team = ws_app_env
    mock_ws = MockControllableWebSocket(app_instance)

    endpoint_task = asyncio.create_task(websocket_endpoint(mock_ws))
    await asyncio.sleep(0.05)

    # Emit from a background thread
    def worker_thread():
        for i in range(5):
            team.emitter.emit(
                AgentEvent(
                    event_type=EventType.TOKEN_STREAM,
                    agent_name="worker",
                    task_id="thread-conv",
                    metadata={"delta": f"chunk-{i} "},
                )
            )

    thread = threading.Thread(target=worker_thread)
    thread.start()
    thread.join()

    await asyncio.sleep(0.1)
    await mock_ws.disconnect()
    await endpoint_task

    token_messages = [msg for msg in mock_ws.sent if msg.get("type") == "token_chunk"]
    assert len(token_messages) == 5
    assert [m["delta"] for m in token_messages] == ["chunk-0 ", "chunk-1 ", "chunk-2 ", "chunk-3 ", "chunk-4 "]


# ---------------------------------------------------------------------------
# 4. Connection Lifecycle & Closed Socket Resilience
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ws_closed_connection_resilience(ws_app_env):
    app_instance, ws, team = ws_app_env

    # 1 failing socket and 1 healthy socket
    broken_ws = MockControllableWebSocket(app_instance, fail_on_send=True)
    healthy_ws = MockControllableWebSocket(app_instance)

    t_broken = asyncio.create_task(websocket_endpoint(broken_ws))
    t_healthy = asyncio.create_task(websocket_endpoint(healthy_ws))
    await asyncio.sleep(0.05)

    assert len(app.state.chat_sockets) == 2

    # Broadcast token stream
    team.emitter.emit(
        AgentEvent(
            event_type=EventType.TOKEN_STREAM,
            agent_name="resilient-agent",
            task_id="conv-resilient",
            metadata={"delta": "Live Token"},
        )
    )

    await asyncio.sleep(0.05)

    # The broken socket should have been discarded without crashing the runtime
    assert broken_ws not in app.state.chat_sockets
    assert healthy_ws in app.state.chat_sockets

    # Healthy socket received the message
    healthy_tokens = [m for m in healthy_ws.sent if m.get("type") == "token_chunk"]
    assert len(healthy_tokens) == 1
    assert healthy_tokens[0]["delta"] == "Live Token"

    await broken_ws.disconnect()
    await healthy_ws.disconnect()
    await t_broken
    await t_healthy


@pytest.mark.asyncio
async def test_ws_join_session_message(ws_app_env):
    app_instance, ws, team = ws_app_env
    mock_ws = MockControllableWebSocket(app_instance)

    endpoint_task = asyncio.create_task(websocket_endpoint(mock_ws))
    await asyncio.sleep(0.05)

    await mock_ws.push_msg(json.dumps({"type": "join_session", "session_id": "conv-dynamically-joined"}))
    await asyncio.sleep(0.05)

    joined_acks = [m for m in mock_ws.sent if m.get("type") == "session_joined"]
    assert len(joined_acks) == 1
    assert joined_acks[0]["session_id"] == "conv-dynamically-joined"

    await mock_ws.disconnect()
    await endpoint_task
