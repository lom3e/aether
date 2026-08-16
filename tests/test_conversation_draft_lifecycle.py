"""
Automated tests for conversation draft lifecycle, immediate creation upon first message send,
and zero ghost conversations.

Cases tested:
- Case A: New Task (draft state) -> 0 conversations in DB.
- Case B: New Task -> Send first message -> conversation exists immediately, user message persisted, prompt temporary title.
- Case C: New Task -> Send -> AI still processing in background -> conversation already visible in history.
- Case D: New Task -> Send -> AI completes -> same conversation contains user + assistant + activities.
- Case E: New Task -> Send -> navigate Home while AI is processing -> conversation already visible in history and unread behaves correctly.
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
async def test_case_a_new_task_draft_creates_no_database_record(tmp_path):
    """Case A: Opening a New Task (draft state) creates 0 records in SQLite."""
    ws_dir = tmp_path / "draft-ws-a"
    ws = Workspace.init(ws_dir, name="Draft Test Workspace A")

    # When in draft mode, no record exists in DB
    convs = ws.conversations.list()
    assert len(convs) == 0


@pytest.mark.asyncio
async def test_case_b_first_send_creates_conversation_immediately_with_temporary_title(tmp_path, monkeypatch):
    """Case B: First Send immediately creates conversation in SQLite with temporary title and user message."""
    ws_dir = tmp_path / "draft-ws-b"
    ws = Workspace.init(ws_dir, name="Draft Test Workspace B")
    PresetApplier().apply_preset("starter-workforce", ws)

    app.state.workspace = ws
    app.state.workspace_root = ws.root
    team = ws.load_team()
    app.state.team = team
    app.state.active_team_name = "default"
    app.state.active_tasks = {}
    app.state.chat_sockets = set()
    app.state.hitl_queues = {}

    started_event = asyncio.Event()

    def slow_run(prompt, session_id):
        started_event.set()
        time.sleep(0.3)
        return ExecutionResult(output="Analysis complete.", success=True)

    monkeypatch.setattr(team, "run", slow_run)

    session_id = "conv_draft_test_case_b"
    mock_ws = MockControllableWebSocket(app)
    ws_task = asyncio.create_task(websocket_endpoint(mock_ws))

    # Send first message
    prompt = "Qual è il ruolo del Manager e come delega i task alla workforce?"
    await mock_ws.push_msg(json.dumps({
        "type": "run_task",
        "content": prompt,
        "session_id": session_id
    }))

    # Wait until task started (while team.run is still running in background)
    await asyncio.sleep(0.08)

    # 1. Conversation exists immediately in SQLite
    convs = ws.conversations.list()
    assert len(convs) == 1
    assert convs[0]["id"] == session_id
    assert "Qual è il ruolo del manager" in convs[0]["title"]
    assert convs[0]["status"] == "active"

    # 2. User message is already persisted
    conv = ws.conversations.get(session_id)
    assert conv is not None
    messages = conv.get("messages", [])
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == prompt

    # Wait for completion
    await asyncio.sleep(0.4)
    await mock_ws.disconnect()
    await ws_task


@pytest.mark.asyncio
async def test_case_c_conversation_visible_in_history_while_ai_processing(tmp_path, monkeypatch):
    """Case C: Conversation is immediately queryable and visible in history while AI is executing."""
    ws_dir = tmp_path / "draft-ws-c"
    ws = Workspace.init(ws_dir, name="Draft Test Workspace C")
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
        time.sleep(0.25)
        return ExecutionResult(output="Finished processing.", success=True)

    monkeypatch.setattr(team, "run", slow_run)

    session_id = "conv_draft_test_case_c"
    mock_ws = MockControllableWebSocket(app)
    ws_task = asyncio.create_task(websocket_endpoint(mock_ws))

    await mock_ws.push_msg(json.dumps({
        "type": "run_task",
        "content": "Analyze competitor strategies",
        "session_id": session_id
    }))

    await asyncio.sleep(0.08)

    # Fetch list while task is running
    convs = ws.conversations.list()
    assert len(convs) == 1
    assert convs[0]["id"] == session_id
    assert convs[0]["status"] == "active"

    # Clean up
    await asyncio.sleep(0.3)
    await mock_ws.disconnect()
    await ws_task


@pytest.mark.asyncio
async def test_case_d_same_conversation_persists_full_cycle(tmp_path, monkeypatch):
    """Case D: AI completion saves assistant message to the EXACT SAME conversation record."""
    ws_dir = tmp_path / "draft-ws-d"
    ws = Workspace.init(ws_dir, name="Draft Test Workspace D")
    PresetApplier().apply_preset("starter-workforce", ws)

    app.state.workspace = ws
    app.state.workspace_root = ws.root
    team = ws.load_team()
    app.state.team = team
    app.state.active_team_name = "default"
    app.state.active_tasks = {}
    app.state.chat_sockets = set()
    app.state.hitl_queues = {}

    def mock_run(prompt, session_id):
        return ExecutionResult(
            output="## Execution Plan\n\n1. Market research\n2. Financial audit",
            success=True,
            metadata={"agent_name": "developer-manager"}
        )

    monkeypatch.setattr(team, "run", mock_run)

    session_id = "conv_draft_test_case_d"
    mock_ws = MockControllableWebSocket(app)
    ws_task = asyncio.create_task(websocket_endpoint(mock_ws))

    await mock_ws.push_msg(json.dumps({
        "type": "run_task",
        "content": "Create roadmap for product launch",
        "session_id": session_id
    }))

    await asyncio.sleep(0.15)

    convs = ws.conversations.list()
    assert len(convs) == 1
    assert convs[0]["id"] == session_id

    conv = ws.conversations.get(session_id)
    assert conv is not None
    assert conv["status"] == "completed"
    messages = conv.get("messages", [])
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert "Execution Plan" in messages[1]["content"]

    await mock_ws.disconnect()
    await ws_task


@pytest.mark.asyncio
async def test_case_e_navigate_home_during_processing_and_unread_lifecycle(tmp_path, monkeypatch):
    """Case E: Sending first message, navigating Home while AI runs, leaves active state and unread indicator."""
    ws_dir = tmp_path / "draft-ws-e"
    ws = Workspace.init(ws_dir, name="Draft Test Workspace E")
    PresetApplier().apply_preset("starter-workforce", ws)

    app.state.workspace = ws
    app.state.workspace_root = ws.root
    team = ws.load_team()
    app.state.team = team
    app.state.active_team_name = "default"
    app.state.active_tasks = {}
    app.state.chat_sockets = set()
    app.state.hitl_queues = {}

    def mock_run(prompt, session_id):
        time.sleep(0.2)
        return ExecutionResult(output="All tests verified.", success=True)

    monkeypatch.setattr(team, "run", mock_run)

    session_id = "conv_draft_test_case_e"
    mock_ws = MockControllableWebSocket(app)
    ws_task = asyncio.create_task(websocket_endpoint(mock_ws))

    # Send first message
    await mock_ws.push_msg(json.dumps({
        "type": "run_task",
        "content": "Run end to end integration tests",
        "session_id": session_id
    }))

    await asyncio.sleep(0.08)

    # Immediately query Home / sidebar list while task is running
    convs_during_run = ws.conversations.list()
    assert len(convs_during_run) == 1
    assert convs_during_run[0]["id"] == session_id
    assert convs_during_run[0]["status"] == "active"
    assert convs_during_run[0]["unread"] is False

    # Wait for completion
    await asyncio.sleep(0.3)

    # After assistant response, conversation is completed and marked unread for background observer
    convs_after_run = ws.conversations.list()
    assert len(convs_after_run) == 1
    assert convs_after_run[0]["status"] == "completed"
    assert convs_after_run[0]["unread"] is True

    # User opens conversation (marks read)
    ws.conversations.mark_read(session_id)
    assert ws.conversations.get(session_id)["unread"] is False

    await mock_ws.disconnect()
    await ws_task
