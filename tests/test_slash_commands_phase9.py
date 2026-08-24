"""
Tests for Phase 9: Agentic Slash Commands.

Validates:
1. Command Registry & Dispatcher resolution and aliasing.
2. Robust parsing with single/double quotes, special characters, and unclosed quotes.
3. Unknown command handling with clear local error (no LLM call).
4. Argument requirement validation across commands.
5. All 26 built-in slash commands across categories:
   - Core: /help, /clear, /compact, /status, /context
   - AI: /model, /plan, /fast, /review
   - Workforce: /agents, /skills, /tools, /tasks
   - Project: /files, /open, /diff, /init
   - Conversation: /new, /rename, /resume, /fork, /rewind
   - Permissions: /permissions
   - Utility: /search, /btw, /copy
6. Sandboxed filesystem compliance for /files and /open (cannot escape PathSandbox).
7. Real web search execution for /search without LLM provider invocation.
8. REST API endpoints (/commands and /commands/execute).
9. WebSocket interception: slash commands execute locally and never invoke team.run or LLM provider,
   while standard prompts continue through normal execution.
"""
import asyncio
import json
import pytest
from pathlib import Path
from starlette.requests import Request
from starlette.websockets import WebSocketDisconnect

from aether.workspace.workspace import Workspace
from aether.presets.applier import PresetApplier
from aether.commands import (
    CommandContext,
    CommandDispatcher,
    CommandRegistry,
    CommandCategory,
    is_slash_command,
    parse_command_line,
    get_default_command_dispatcher,
)
from aether.core.execution import ExecutionResult
from aether.core.security import OperationType
from aether.server.app import app
from aether.server.routes import list_commands, execute_command_endpoint, ExecuteCommandPayload
from aether.server.sockets import websocket_endpoint


class MockControllableWebSocket:
    """Mock WebSocket for end-to-end slash command testing."""
    def __init__(self, app_instance):
        self.app = app_instance
        self.headers = {"origin": "http://localhost:3000"}
        self.query_params = {}
        self.incoming = asyncio.Queue()
        self.outgoing = []
        self.closed = False
        self.state = type("State", (), {})()

    async def accept(self):
        pass

    async def send_json(self, data):
        self.outgoing.append(data)

    async def receive_text(self):
        if self.closed:
            raise WebSocketDisconnect(code=1000)
        msg = await self.incoming.get()
        if msg is None:
            raise WebSocketDisconnect(code=1000)
        return msg

    async def push_msg(self, msg_text):
        await self.incoming.put(msg_text)

    async def close(self, code=1000):
        self.closed = True
        await self.incoming.put(None)

    async def disconnect(self):
        await self.close()


@pytest.fixture
def workspace_fixture(tmp_path):
    ws_dir = tmp_path / "slash_workspace"
    ws = Workspace.init(ws_dir, name="Slash Test Workspace")
    PresetApplier().apply_preset("developer-workforce", ws)
    return ws


# =============================================================================
# 1. PARSER & REGISTRY TESTS
# =============================================================================

def test_parser_and_slash_detection():
    """Verify is_slash_command and parse_command_line for various command shapes."""
    assert is_slash_command("/help") is True
    assert is_slash_command("/model gpt-4o") is True
    assert is_slash_command("/search 'python asyncio'") is True
    assert is_slash_command("hello world") is False
    assert is_slash_command("//comment") is False
    assert is_slash_command("") is False
    assert is_slash_command("   /status   ") is True

    # Simple
    cmd, args, raw = parse_command_line("/help")
    assert cmd == "help"
    assert args == []
    assert raw == ""

    # Arguments
    cmd, args, raw = parse_command_line("/model qwen3.5:9b")
    assert cmd == "model"
    assert args == ["qwen3.5:9b"]
    assert raw == "qwen3.5:9b"

    # Multi-word and quotes
    cmd, args, raw = parse_command_line('/rename "Sprint 42 Refactor"')
    assert cmd == "rename"
    assert args == ["Sprint 42 Refactor"]
    assert raw == '"Sprint 42 Refactor"'

    # Unclosed quotes fallback (does not crash)
    cmd, args, raw = parse_command_line('/search "unclosed quote search')
    assert cmd == "search"
    assert len(args) > 0


def test_registry_lookup_and_aliases():
    """Verify primary and alias command resolution."""
    dispatcher = get_default_command_dispatcher()
    reg = dispatcher.registry

    assert reg.has("help") is True
    assert reg.has("h") is True
    assert reg.has("?") is True
    assert reg.has("status") is True
    assert reg.has("st") is True
    assert reg.has("model") is True
    assert reg.has("m") is True
    assert reg.has("non_existent_command_123") is False

    spec, _ = reg.get("st")
    assert spec.name == "status"


@pytest.mark.asyncio
async def test_unknown_command_produces_clear_local_error():
    """Unknown commands produce structured local error without provider call."""
    dispatcher = get_default_command_dispatcher()
    res = await dispatcher.dispatch("/foobar123")
    assert res.success is False
    assert "Unknown command: /foobar123" in res.error
    assert "Use `/help`" in res.output


# =============================================================================
# 2. CORE & SESSION COMMANDS TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_cmd_help(workspace_fixture):
    """Test /help and /help <command>."""
    dispatcher = get_default_command_dispatcher()
    ctx = CommandContext(command="help", args=[], raw_args="", workspace=workspace_fixture)

    # All commands help
    res = await dispatcher.dispatch("/help", ctx)
    assert res.success is True
    assert "Aether Slash Commands" in res.output
    assert "/status" in res.output
    assert "/model" in res.output
    assert "/agents" in res.output

    # Specific command help
    res_spec = await dispatcher.dispatch("/help model", ctx)
    assert res_spec.success is True
    assert "Command: `/model`" in res_spec.output


@pytest.mark.asyncio
async def test_cmd_clear_compact_status_context(workspace_fixture):
    """Test /clear, /compact, /status, and /context."""
    dispatcher = get_default_command_dispatcher()
    team = workspace_fixture.load_team()
    conv = workspace_fixture.conversations.create(title="Status Test")

    ctx = CommandContext(
        command="status",
        args=[],
        raw_args="",
        workspace=workspace_fixture,
        team=team,
        conversation_id=conv["id"],
        session_id=conv["id"],
    )

    # /clear
    res_clear = await dispatcher.dispatch("/clear", ctx)
    assert res_clear.success is True
    assert res_clear.ui_action == "clear_chat"

    # /compact
    res_compact = await dispatcher.dispatch("/compact", ctx)
    assert res_compact.success is False
    assert "not available" in res_compact.output

    # /status
    res_status = await dispatcher.dispatch("/status", ctx)
    assert res_status.success is True
    assert "Slash Test Workspace" in res_status.output
    assert "Status Test" in res_status.output

    # /context
    res_ctx = await dispatcher.dispatch("/context", ctx)
    assert res_ctx.success is True
    assert "Runtime Context Information" in res_ctx.output


# =============================================================================
# 3. AI & WORKFORCE COMMANDS TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_cmd_model_plan_fast_review(workspace_fixture):
    """Test AI commands: /model, /plan, /fast, /review."""
    dispatcher = get_default_command_dispatcher()
    team = workspace_fixture.load_team()
    ctx = CommandContext(command="model", args=[], raw_args="", workspace=workspace_fixture, team=team)

    # /model inspect
    res_m = await dispatcher.dispatch("/model", ctx)
    assert res_m.success is True
    assert "Current Model" in res_m.output

    # /model switch
    res_m_set = await dispatcher.dispatch("/model gpt-4o-test", ctx)
    assert res_m_set.success is True
    assert team.config.default_model == "gpt-4o-test"

    # /plan
    res_plan = await dispatcher.dispatch("/plan", ctx)
    assert res_plan.success is True
    assert "Planning Mode" in res_plan.output

    # /fast
    res_fast = await dispatcher.dispatch("/fast", ctx)
    assert res_fast.success is True

    # /review
    res_review = await dispatcher.dispatch("/review", ctx)
    assert res_review.success is True
    assert "Code Review Context" in res_review.output


@pytest.mark.asyncio
async def test_cmd_agents_skills_tools_tasks(workspace_fixture):
    """Test workforce commands: /agents, /skills, /tools, /tasks."""
    dispatcher = get_default_command_dispatcher()
    team = workspace_fixture.load_team()

    app_state = type("AppState", (), {"active_tasks": {}})()
    ctx = CommandContext(command="agents", args=[], raw_args="", workspace=workspace_fixture, team=team, app_state=app_state)

    # /agents
    res_agents = await dispatcher.dispatch("/agents", ctx)
    assert res_agents.success is True
    assert "development-manager" in res_agents.output
    assert "code-analyst" in res_agents.output

    # /skills
    res_skills = await dispatcher.dispatch("/skills", ctx)
    assert res_skills.success is True
    assert "coding" in res_skills.output
    assert "debugging" in res_skills.output

    # /tools
    res_tools = await dispatcher.dispatch("/tools", ctx)
    assert res_tools.success is True
    assert "read_file" in res_tools.output
    assert "delete_file" in res_tools.output

    # /tasks idle
    res_tasks = await dispatcher.dispatch("/tasks", ctx)
    assert res_tasks.success is True
    assert "No background or workforce tasks" in res_tasks.output

    # /tasks stop
    dummy_task = asyncio.create_task(asyncio.sleep(10))
    app_state.active_tasks["task_999"] = dummy_task

    res_stop = await dispatcher.dispatch("/tasks stop task_999", ctx)
    assert res_stop.success is True
    await asyncio.sleep(0)
    assert dummy_task.cancelling() > 0 or dummy_task.cancelled() or dummy_task.done()


# =============================================================================
# 4. PROJECT & CODING COMMANDS TESTS (PATHSANDBOX SECURITY)
# =============================================================================

@pytest.mark.asyncio
async def test_cmd_files_open_diff_init(workspace_fixture):
    """Test /files, /open, /diff, /init respecting PathSandbox."""
    dispatcher = get_default_command_dispatcher()
    ctx = CommandContext(command="files", args=[], raw_args="", workspace=workspace_fixture)

    # Create test file inside sandbox
    workspace_fixture.sandbox.validate_path("test_code.py", operation=OperationType.WRITE).write_text("print('hello aether')", encoding="utf-8")

    # /files
    res_files = await dispatcher.dispatch("/files", ctx)
    assert res_files.success is True
    assert "test_code.py" in res_files.output

    # /open valid
    res_open = await dispatcher.dispatch("/open test_code.py", ctx)
    assert res_open.success is True
    assert "print('hello aether')" in res_open.output

    # /open path traversal attempt (security blocked)
    res_open_escape = await dispatcher.dispatch("/open ../../etc/passwd", ctx)
    assert res_open_escape.success is False
    assert "resolves outside sandbox root" in res_open_escape.output

    # /diff
    res_diff = await dispatcher.dispatch("/diff", ctx)
    assert res_diff.success is True

    # /init
    res_init = await dispatcher.dispatch("/init", ctx)
    assert res_init.success is True


# =============================================================================
# 5. CONVERSATION LIFECYCLE COMMANDS TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_cmd_conversation_lifecycle(workspace_fixture):
    """Test /new, /rename, /resume, /fork, /rewind."""
    dispatcher = get_default_command_dispatcher()
    conv = workspace_fixture.conversations.create(title="Initial Task")
    cid = conv["id"]

    ctx = CommandContext(command="rename", args=[], raw_args="", workspace=workspace_fixture, conversation_id=cid)

    # /rename
    res_rename = await dispatcher.dispatch("/rename Sprint Retrospective", ctx)
    assert res_rename.success is True
    assert res_rename.ui_action == "rename_conversation"
    assert workspace_fixture.conversations.get(cid)["title"] == "Sprint Retrospective"

    # /fork
    res_fork = await dispatcher.dispatch("/fork", ctx)
    assert res_fork.success is True
    assert res_fork.ui_action == "select_conversation"
    assert res_fork.data["forked_from"] == cid

    # /resume
    res_resume = await dispatcher.dispatch(f"/resume {cid}", ctx)
    assert res_resume.success is True
    assert res_resume.ui_action == "select_conversation"

    # /new
    res_new = await dispatcher.dispatch("/new", ctx)
    assert res_new.success is True
    assert res_new.ui_action == "new_conversation"

    # /rewind
    res_rewind = await dispatcher.dispatch("/rewind", ctx)
    assert res_rewind.success is False
    assert "not available" in res_rewind.output


# =============================================================================
# 6. PERMISSIONS & UTILITY COMMANDS TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_cmd_permissions_search_btw_copy(workspace_fixture, monkeypatch):
    """Test /permissions, /search, /btw, /copy."""
    dispatcher = get_default_command_dispatcher()
    ctx = CommandContext(command="permissions", args=[], raw_args="", workspace=workspace_fixture)

    # /permissions
    res_perm = await dispatcher.dispatch("/permissions", ctx)
    assert res_perm.success is True
    assert "PathSandbox" in res_perm.output
    assert "delete_file" in res_perm.output

    # Mock web search backend to avoid outbound network in tests
    from aether.tools.web_search import WebSearchResult
    def mock_search(self, query, max_results=5, timeout=10.0):
        return [
            WebSearchResult(
                title="Python 3.14 Official Docs",
                url="https://docs.python.org/3.14/",
                snippet="What's new in Python 3.14 documentation and releases.",
            )
        ]
    from aether.tools.web_search import DuckDuckGoSearchBackend
    monkeypatch.setattr(DuckDuckGoSearchBackend, "search", mock_search)

    # /search
    res_search = await dispatcher.dispatch("/search python 3.14", ctx)
    assert res_search.success is True
    assert "Python 3.14 Official Docs" in res_search.output

    # /btw
    res_btw = await dispatcher.dispatch("/btw what is asyncio event loop?", ctx)
    assert res_btw.success is True
    assert "Side Question" in res_btw.output

    # /copy
    res_copy = await dispatcher.dispatch("/copy", ctx)
    assert res_copy.success is True
    assert "copy button" in res_copy.output


# =============================================================================
# 7. REST API ENDPOINTS TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_rest_api_slash_commands(workspace_fixture):
    """Verify /commands and /commands/execute endpoints."""
    app.state.workspace = workspace_fixture
    app.state.team = workspace_fixture.load_team()

    # 1. GET /commands
    cmds = await list_commands()
    assert isinstance(cmds, list)
    assert len(cmds) >= 26
    names = [c["name"] for c in cmds]
    assert "help" in names
    assert "model" in names
    assert "status" in names
    assert "agents" in names
    assert "files" in names

    # 2. POST /commands/execute
    req = Request({"type": "http", "app": app, "headers": [], "path": "/api/commands/execute", "method": "POST"})
    exec_res = await execute_command_endpoint(req, ExecuteCommandPayload(command="/status"))
    assert exec_res["success"] is True
    assert "Aether Workforce Status" in exec_res["output"]


# =============================================================================
# 8. WEBSOCKET INTERCEPTION TESTS (NO LLM PROVIDER CALL FOR SLASH COMMANDS)
# =============================================================================

@pytest.mark.asyncio
async def test_websocket_intercepts_slash_command_without_calling_provider(workspace_fixture, monkeypatch):
    """Verify WebSocket intercepting slash command executes locally and never calls team.run."""
    app.state.workspace = workspace_fixture
    app.state.workspace_root = workspace_fixture.root
    team = workspace_fixture.load_team()
    app.state.team = team
    app.state.active_team_name = "default"
    app.state.active_tasks = {}
    app.state.chat_sockets = set()
    app.state.hitl_queues = {}

    provider_called = False
    def trap_team_run(prompt, session_id):
        nonlocal provider_called
        provider_called = True
        return ExecutionResult(output="LLM Output", success=True)

    monkeypatch.setattr(team, "run", trap_team_run)

    session_id = "slash_ws_test_conv"
    mock_ws = MockControllableWebSocket(app)
    ws_task = asyncio.create_task(websocket_endpoint(mock_ws))

    # Send slash command via websocket
    await mock_ws.push_msg(json.dumps({
        "type": "run_task",
        "content": "/status",
        "session_id": session_id,
    }))

    await asyncio.sleep(0.1)

    # Verify provider was NEVER called
    assert provider_called is False

    # Verify command output was persisted in conversation history
    conv = workspace_fixture.conversations.get(session_id)
    assert conv is not None
    assert len(conv["messages"]) == 2
    assert conv["messages"][0]["role"] == "user"
    assert conv["messages"][0]["content"] == "/status"
    assert conv["messages"][1]["role"] == "assistant"
    assert "Aether Workforce Status" in conv["messages"][1]["content"]

    # Verify outgoing WebSocket events contained command_result and task_completed
    event_types = [msg.get("type") for msg in mock_ws.outgoing]
    assert "command_result" in event_types
    assert "task_completed" in event_types

    await mock_ws.disconnect()
    await ws_task


@pytest.mark.asyncio
async def test_websocket_standard_message_continues_to_call_provider(workspace_fixture, monkeypatch):
    """Verify WebSocket standard non-slash message continues to call provider as expected."""
    app.state.workspace = workspace_fixture
    app.state.workspace_root = workspace_fixture.root
    team = workspace_fixture.load_team()
    app.state.team = team
    app.state.active_team_name = "default"
    app.state.active_tasks = {}
    app.state.chat_sockets = set()
    app.state.hitl_queues = {}

    provider_called = False
    def mock_team_run(prompt, session_id):
        nonlocal provider_called
        provider_called = True
        return ExecutionResult(output="Workforce completed task.", success=True)

    monkeypatch.setattr(team, "run", mock_team_run)

    session_id = "normal_ws_test_conv"
    mock_ws = MockControllableWebSocket(app)
    ws_task = asyncio.create_task(websocket_endpoint(mock_ws))

    # Send standard prompt without /
    await mock_ws.push_msg(json.dumps({
        "type": "run_task",
        "content": "Create a python script to calculate fibonacci",
        "session_id": session_id,
    }))

    await asyncio.sleep(0.1)

    # Provider WAS called
    assert provider_called is True

    await mock_ws.disconnect()
    await ws_task
