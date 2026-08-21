"""
Comprehensive tests for P0 Chat Reliability:
- Error normalization & categorization
- Ollama ModelNotFoundError on HTTP 404
- Error message persistence in SQLite ConversationStore
- WebSocket error broadcast with structured payload
- Retry without duplicate messages
- Provider setting persistence & in-memory team reloading
"""
import asyncio
import io
import json
import urllib.error
import pytest
from fastapi import WebSocketDisconnect
from starlette.requests import Request

from aether.core.execution import ExecutionResult
from aether.presets.applier import PresetApplier
from aether.providers.errors import (
    AuthenticationError,
    ModelNotFoundError,
    ProviderConnectionError,
    ProviderNotFoundError,
    RateLimitError,
    TimeoutError,
    normalize_provider_error,
)
from aether.providers.ollama import OllamaProvider
from aether.providers.types import ProviderConfig
from aether.server.app import app
from aether.server.routes import save_provider_settings, ProviderSettings
from aether.server.sockets import websocket_endpoint
from aether.workspace.workspace import Workspace


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


# ---------------------------------------------------------------------------
# 1. Error Normalization Unit Tests
# ---------------------------------------------------------------------------

def test_normalize_provider_error_categories():
    """Verify normalize_provider_error produces standardized error structures."""
    # 1. Authentication
    auth_err = AuthenticationError("Invalid API key", provider="openai")
    norm_auth = normalize_provider_error(auth_err, provider="openai")
    assert norm_auth["code"] == "AUTHENTICATION_ERROR"
    assert norm_auth["retryable"] is False
    assert norm_auth["provider"] == "openai"

    # 2. Rate Limit
    rate_err = RateLimitError("Rate limit exceeded", provider="anthropic")
    norm_rate = normalize_provider_error(rate_err, provider="anthropic")
    assert norm_rate["code"] == "RATE_LIMIT_ERROR"
    assert norm_rate["retryable"] is True

    # 3. Timeout
    timeout_err = TimeoutError("Timed out after 120s", provider="ollama")
    norm_timeout = normalize_provider_error(timeout_err, provider="ollama")
    assert norm_timeout["code"] == "TIMEOUT"
    assert norm_timeout["retryable"] is True

    # 4. Model Unavailable
    model_err = ModelNotFoundError("model 'qwen3:14b' not found", provider="ollama")
    norm_model = normalize_provider_error(model_err, provider="ollama", model="qwen3:14b")
    assert norm_model["code"] == "MODEL_UNAVAILABLE"
    assert norm_model["retryable"] is True
    assert "qwen3:14b" in norm_model["message"]

    # 5. Provider Connection / Unavailable
    conn_err = ProviderConnectionError("Could not connect to Ollama", provider="ollama")
    norm_conn = normalize_provider_error(conn_err, provider="ollama")
    assert norm_conn["code"] == "PROVIDER_UNAVAILABLE"
    assert norm_conn["retryable"] is True

    # 6. Provider Not Found
    p_not_found = ProviderNotFoundError("unknown_provider", provider="unknown_provider")
    norm_pnf = normalize_provider_error(p_not_found, provider="unknown_provider")
    assert norm_pnf["code"] == "PROVIDER_NOT_FOUND"
    assert norm_pnf["retryable"] is False

    # 7. Generic / Runtime Error
    gen_err = ValueError("Unexpected computation failure")
    norm_gen = normalize_provider_error(gen_err, provider="ollama")
    assert norm_gen["code"] == "TASK_FAILED"
    assert norm_gen["retryable"] is True
    assert norm_gen["technical_details"] == "Unexpected computation failure"


# ---------------------------------------------------------------------------
# 2. Ollama Provider HTTP 404 Handling
# ---------------------------------------------------------------------------

def test_ollama_404_raises_model_not_found_error(monkeypatch):
    """When Ollama returns 404, OllamaProvider raises ModelNotFoundError with parsed body."""
    error_body = b'{"error": "model \'qwen3:14b\' not found, try pulling it first"}'
    fp = io.BytesIO(error_body)
    http_error = urllib.error.HTTPError(
        url="http://localhost:11434/api/chat",
        code=404,
        msg="Not Found",
        hdrs=None,
        fp=fp,
    )

    def mock_urlopen(req, timeout=None):
        raise http_error

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    provider = OllamaProvider(config=ProviderConfig(model="qwen3:14b"))
    with pytest.raises(ModelNotFoundError) as exc_info:
        provider.generate([])

    assert "model 'qwen3:14b' not found" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 3. WebSocket Task Failure Persistence & Broadcast
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_websocket_task_failure_persists_error_message(tmp_path, monkeypatch):
    """When team execution fails, assistant error message is saved and broadcasted."""
    ws_dir = tmp_path / "chat-fail-ws"
    ws = Workspace.init(ws_dir, name="Chat Reliability WS")
    PresetApplier().apply_preset("starter-workforce", ws)

    app.state.workspace = ws
    app.state.workspace_root = ws.root
    team = ws.load_team()
    app.state.team = team
    app.state.active_team_name = "default"
    app.state.active_tasks = {}
    app.state.chat_sockets = set()
    app.state.hitl_queues = {}

    # Simulate failing execution
    def fail_run(prompt, session_id):
        return ExecutionResult(
            output=None,
            success=False,
            error="Ollama HTTP error 404: model 'qwen3:14b' not found, try pulling it first",
        )

    monkeypatch.setattr(team, "run", fail_run)

    session_id = "conv_fail_test_101"
    mock_ws = MockControllableWebSocket(app)

    ws_task = asyncio.create_task(websocket_endpoint(mock_ws))

    # Send run_task
    await mock_ws.push_msg(json.dumps({
        "type": "run_task",
        "content": "Hello Aether workforce",
        "session_id": session_id,
    }))
    await asyncio.sleep(0.15)

    # 1. Verify conversation status is failed
    conv = ws.conversations.get(session_id)
    assert conv is not None
    assert conv["status"] == "failed"

    # 2. Verify messages list contains the user prompt and the assistant error card message
    msgs = conv["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Hello Aether workforce"

    assistant_msg = msgs[1]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg.get("metadata") is not None
    assert assistant_msg["metadata"].get("is_error") is True
    assert assistant_msg["metadata"]["error"]["code"] == "MODEL_UNAVAILABLE"
    assert assistant_msg["metadata"]["error"]["retryable"] is True

    # 3. Verify WebSocket broadcast payload
    completed_events = [e for e in mock_ws.sent if e.get("type") == "task_completed"]
    assert len(completed_events) == 1
    ev = completed_events[0]
    assert ev["success"] is False
    assert ev["session_id"] == session_id
    assert ev["error_details"]["code"] == "MODEL_UNAVAILABLE"

    await mock_ws.disconnect()
    await ws_task


# ---------------------------------------------------------------------------
# 4. WebSocket Retry Flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_websocket_retry_response_flow(tmp_path, monkeypatch):
    """When retrying a failed turn, previous error is truncated and successful answer is stored."""
    ws_dir = tmp_path / "chat-retry-ws"
    ws = Workspace.init(ws_dir, name="Chat Retry WS")
    PresetApplier().apply_preset("starter-workforce", ws)

    app.state.workspace = ws
    app.state.workspace_root = ws.root
    team = ws.load_team()
    app.state.team = team
    app.state.active_team_name = "default"
    app.state.active_tasks = {}
    app.state.chat_sockets = set()
    app.state.hitl_queues = {}

    call_count = 0

    def mock_run_flaky(prompt, session_id):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return ExecutionResult(output=None, success=False, error="Connection refused")
        return ExecutionResult(output="Task completed successfully after retry!", success=True)

    monkeypatch.setattr(team, "run", mock_run_flaky)

    session_id = "conv_retry_test_202"
    mock_ws = MockControllableWebSocket(app)

    ws_task = asyncio.create_task(websocket_endpoint(mock_ws))

    # Turn 1: fails
    await mock_ws.push_msg(json.dumps({
        "type": "run_task",
        "content": "Analyze my data",
        "session_id": session_id,
    }))
    await asyncio.sleep(0.15)

    conv_after_fail = ws.conversations.get(session_id)
    assert conv_after_fail["status"] == "failed"
    assert len(conv_after_fail["messages"]) == 2
    assert conv_after_fail["messages"][1]["metadata"].get("is_error") is True

    # Turn 2: send retry_response
    await mock_ws.push_msg(json.dumps({
        "type": "retry_response",
        "session_id": session_id,
    }))
    await asyncio.sleep(0.15)

    conv_after_retry = ws.conversations.get(session_id)
    assert conv_after_retry["status"] == "completed"
    # Must contain exactly 1 user message and 1 successful assistant message (failed message replaced)
    assert len(conv_after_retry["messages"]) == 2
    assert conv_after_retry["messages"][0]["role"] == "user"
    assert conv_after_retry["messages"][1]["role"] == "assistant"
    assert conv_after_retry["messages"][1]["content"] == "Task completed successfully after retry!"
    assert conv_after_retry["messages"][1].get("metadata") is None or not conv_after_retry["messages"][1].get("metadata", {}).get("is_error")

    await mock_ws.disconnect()
    await ws_task


# ---------------------------------------------------------------------------
# 5. Provider Setting Persistence & In-Memory Team Re-instantiation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_provider_settings_reloads_team_in_memory(tmp_path):
    """Saving provider settings updates YAML and immediately reloads app.state.team in memory."""
    ws_dir = tmp_path / "provider-reload-ws"
    ws = Workspace.init(ws_dir, name="Provider Reload WS")
    PresetApplier().apply_preset("starter-workforce", ws)

    app.state.workspace = ws
    app.state.workspace_root = ws.root
    app.state.team = ws.load_team("starter-workforce")
    app.state.active_team_name = "starter-workforce"

    # Initial state
    assert app.state.team.config.default_model != "qwen3.5:14b-custom"

    req = Request({
        "type": "http",
        "app": app,
        "headers": [],
        "path": "/api/settings/provider",
        "method": "POST",
    })
    resp = await save_provider_settings(req, ProviderSettings(
        provider="ollama",
        model="qwen3.5:14b-custom",
        timeout=180,
    ))
    assert resp == {"status": "ok"}

    # Verify app.state.team was immediately reloaded in memory with the new model
    assert app.state.team.config.default_model == "qwen3.5:14b-custom"
    entry_agent = app.state.team.config.entry_agent()
    active_agent = next((a for a in app.state.team.agents() if a.name == entry_agent.name), None)
    assert active_agent is not None
    assert active_agent.provider.config.model == "qwen3.5:14b-custom"

# ---------------------------------------------------------------------------
# 6. Model Metadata Transparency on Success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_successful_task_records_model_and_provider_metadata(tmp_path, monkeypatch):
    """When a task succeeds, assistant message metadata explicitly records the executed model."""
    ws_dir = tmp_path / "chat-meta-ws"
    ws = Workspace.init(ws_dir, name="Chat Meta WS")
    PresetApplier().apply_preset("starter-workforce", ws)

    app.state.workspace = ws
    app.state.workspace_root = ws.root
    team = ws.load_team("starter-workforce")
    app.state.team = team
    app.state.active_team_name = "starter-workforce"
    app.state.active_tasks = {}
    app.state.chat_sockets = set()
    app.state.hitl_queues = {}

    def mock_run_success(prompt, session_id):
        return ExecutionResult(
            output="Report generated successfully.",
            success=True,
            metadata={"agent_name": "manager", "provider_model": "qwen3.5:9b"},
        )

    monkeypatch.setattr(team, "run", mock_run_success)

    session_id = "conv_meta_test_301"
    mock_ws = MockControllableWebSocket(app)
    ws_task = asyncio.create_task(websocket_endpoint(mock_ws))

    await mock_ws.push_msg(json.dumps({
        "type": "run_task",
        "content": "Create report",
        "session_id": session_id,
    }))
    await asyncio.sleep(0.15)

    conv = ws.conversations.get(session_id)
    assert conv is not None
    assert conv["status"] == "completed"
    msgs = conv["messages"]
    assert len(msgs) == 2
    assistant_msg = msgs[1]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["metadata"]["model"] == "qwen3.5:9b"
    assert assistant_msg["metadata"]["requested_model"] == "qwen3.5:9b"
    assert assistant_msg["metadata"]["provider"] == "ollama"

    completed_events = [e for e in mock_ws.sent if e.get("type") == "task_completed"]
    assert len(completed_events) == 1
    assert completed_events[0]["model"] == "qwen3.5:9b"

    await mock_ws.disconnect()
    await ws_task


# ---------------------------------------------------------------------------
# 7. Model Fallback Transparency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_task_with_fallback_model_records_both_requested_and_executed_models(tmp_path, monkeypatch):
    """When provider returns a fallback model, both executed and requested models are recorded."""
    ws_dir = tmp_path / "chat-fallback-ws"
    ws = Workspace.init(ws_dir, name="Chat Fallback WS")
    PresetApplier().apply_preset("starter-workforce", ws, model="qwen3.5:0.8b")

    app.state.workspace = ws
    app.state.workspace_root = ws.root
    team = ws.load_team("starter-workforce")
    app.state.team = team
    app.state.active_team_name = "starter-workforce"
    app.state.active_tasks = {}
    app.state.chat_sockets = set()
    app.state.hitl_queues = {}

    # Team requested qwen3.5:0.8b, but provider executed qwen3:2.14b
    def mock_run_fallback(prompt, session_id):
        return ExecutionResult(
            output="Response from alternative model.",
            success=True,
            metadata={"agent_name": "manager", "provider_model": "qwen3:2.14b"},
        )

    monkeypatch.setattr(team, "run", mock_run_fallback)

    session_id = "conv_fallback_test_401"
    mock_ws = MockControllableWebSocket(app)
    ws_task = asyncio.create_task(websocket_endpoint(mock_ws))

    await mock_ws.push_msg(json.dumps({
        "type": "run_task",
        "content": "Hello fallback test",
        "session_id": session_id,
    }))
    await asyncio.sleep(0.15)

    conv = ws.conversations.get(session_id)
    assert conv is not None
    msgs = conv["messages"]
    assistant_msg = msgs[1]
    assert assistant_msg["metadata"]["model"] == "qwen3:2.14b"
    assert assistant_msg["metadata"]["requested_model"] == "qwen3.5:0.8b"

    completed_events = [e for e in mock_ws.sent if e.get("type") == "task_completed"]
    assert len(completed_events) == 1
    assert completed_events[0]["model"] == "qwen3:2.14b"

    await mock_ws.disconnect()
    await ws_task


# ---------------------------------------------------------------------------
# 8. Ollama 0 Models Available Handling
# ---------------------------------------------------------------------------

def test_ollama_empty_available_models(monkeypatch):
    """When Ollama has 0 models installed, get_available_models returns empty list gracefully."""
    empty_body = b'{"models": []}'
    fp = io.BytesIO(empty_body)

    def mock_urlopen(req, timeout=None):
        return fp

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    provider = OllamaProvider()
    models = provider.get_available_models()
    assert models == []

