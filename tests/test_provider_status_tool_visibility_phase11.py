"""
test_provider_status_tool_visibility_phase11.py

Tests for:
- P1-03: Provider Status Foundation (health checks, reachable status, caching/TTL, API endpoints)
- P1-08: Tool Visibility Foundation (runtime registry truth, tool visibility in agents/workspace API, /tools & /status integration)
"""
import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import pytest
from starlette.requests import Request

from aether.agents.agent import Agent
from aether.commands.dispatcher import get_default_command_dispatcher
from aether.commands.models import CommandContext
from aether.knowledge.store import KnowledgeStore
from aether.presets.applier import PresetApplier
from aether.providers.health import (
    ProviderHealthChecker,
    ProviderHealthStatus,
    get_default_health_checker,
)
from aether.server.app import app
from aether.server.routes import (
    AgentPayload,
    create_agent,
    get_agents,
    get_provider_status,
    get_workspace,
    update_agent,
)
from aether.team.config import AgentConfig, Relationship, TeamConfig
from aether.team.loader import TeamLoader
from aether.team.team import Team
from aether.tools.base import Tool
from aether.tools.registry import ToolRegistry
from aether.workspace.workspace import Workspace


# ==============================================================================
# 1. Provider Status Foundation Tests (P1-03)
# ==============================================================================

def test_provider_health_status_dataclass():
    """Verify ProviderHealthStatus properties and dictionary conversion."""
    status = ProviderHealthStatus(
        provider="ollama",
        model="llama3.2",
        status="connected",
        reachable=True,
        latency_ms=15.421,
        details={"server_version": "0.5.12"},
    )
    assert status.provider == "ollama"
    assert status.model == "llama3.2"
    assert status.status == "connected"
    assert status.reachable is True
    assert status.latency_ms == 15.421

    d = status.to_dict()
    assert d["provider"] == "ollama"
    assert d["model"] == "llama3.2"
    assert d["status"] == "connected"
    assert d["reachable"] is True
    assert d["latency_ms"] == 15.42
    assert d["error"] is None
    assert d["details"] == {"server_version": "0.5.12"}


def test_provider_health_mock_provider():
    """Mock provider is always reported as connected and reachable."""
    checker = ProviderHealthChecker(ttl_seconds=1.0)
    status = checker.check_health("mock", model="test-model")
    assert status.provider == "mock"
    assert status.status == "connected"
    assert status.reachable is True
    assert status.latency_ms is not None
    assert status.error is None


def test_provider_health_unconfigured_cloud_provider():
    """Cloud providers without API key return 'unconfigured' status without crashing."""
    checker = ProviderHealthChecker(ttl_seconds=1.0)
    with patch.dict("os.environ", {}, clear=True):
        status = checker.check_health("openai", model="gpt-4o", api_key=None)
        assert status.provider == "openai"
        assert status.status == "unconfigured"
        assert status.reachable is False
        assert "API key not configured" in (status.error or "")

        status_anthropic = checker.check_health("anthropic", model="claude-3-5-sonnet-20241022", api_key="")
        assert status_anthropic.status == "unconfigured"
        assert status_anthropic.reachable is False

        status_gemini = checker.check_health("gemini", model="gemini-2.0-flash", api_key="")
        assert status_gemini.status == "unconfigured"
        assert status_gemini.reachable is False


def test_provider_health_ollama_reachable():
    """Ollama server responding 200 is marked as connected."""
    checker = ProviderHealthChecker(ttl_seconds=1.0)

    class MockHTTPResponse:
        def __init__(self, body: bytes):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MockHTTPResponse(b'{"version": "0.5.12"}')
        status = checker.check_health("ollama", model="llama3.2", base_url="http://localhost:11434")
        assert status.provider == "ollama"
        assert status.status == "connected"
        assert status.reachable is True
        assert status.latency_ms is not None
        assert status.error is None
        assert status.details.get("server_version") == "0.5.12"


def test_provider_health_ollama_unreachable_connection_refused():
    """Ollama connection error or refused connection is caught gracefully."""
    checker = ProviderHealthChecker(ttl_seconds=1.0)
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        status = checker.check_health("ollama", model="llama3.2", base_url="http://localhost:11434")
        assert status.provider == "ollama"
        assert status.status == "error"
        assert status.reachable is False
        assert "Connection refused" in (status.error or "")


def test_provider_health_caching_and_force_refresh():
    """Checker caches results within TTL and bypasses cache when force_refresh=True."""
    checker = ProviderHealthChecker(ttl_seconds=5.0)

    calls = 0

    def mock_urlopen_fn(req, **kwargs):
        nonlocal calls
        calls += 1
        class MockResp:
            def read(self):
                return b'{"version": "1.0.0"}'
            def __enter__(self): return self
            def __exit__(self, *args): pass
        return MockResp()

    with patch("urllib.request.urlopen", side_effect=mock_urlopen_fn):
        s1 = checker.check_health("ollama", model="m1", base_url="http://localhost:11434")
        assert calls == 2  # /api/version and /api/tags

        # Second call within TTL should return cached status without new urlopen
        s2 = checker.check_health("ollama", model="m1", base_url="http://localhost:11434")
        assert calls == 2
        assert s2.checked_at == s1.checked_at

        # Force refresh should bypass cache
        s3 = checker.check_health("ollama", model="m1", base_url="http://localhost:11434", force_refresh=True)
        assert calls == 4


@pytest.mark.asyncio
async def test_provider_status_api_endpoint(tmp_path: Path):
    """GET /provider/status and GET /settings/provider/status return valid status contract."""
    ws = Workspace.get_or_init(tmp_path, "Status WS")
    PresetApplier().apply_preset("starter-workforce", ws, set_as_default=True)
    app.state.workspace = ws
    app.state.team = ws.load_team()

    req = Request({"type": "http", "app": app})
    res = await get_provider_status(req, provider="mock", model="mock-model")

    assert res["provider"] == "mock"
    assert res["model"] == "mock-model"
    assert res["status"] == "connected"
    assert res["reachable"] is True
    assert "checked_at" in res


# ==============================================================================
# 2. Tool Visibility Foundation Tests (P1-08)
# ==============================================================================

def test_agent_available_tools_empty():
    """An agent with no tools registered reports an empty tool list."""
    agent = Agent(name="solo-agent", role="Observer")
    assert agent.available_tools() == []


def test_agent_available_tools_single_and_multiple():
    """Agent returns all registered tools from tool_registry."""
    registry = ToolRegistry()

    class CustomTool1(Tool):
        name = "custom_tool_1"
        description = "First tool"
        def execute(self, input_data: str, context=None) -> str:
            return "ok1"

    class CustomTool2(Tool):
        name = "custom_tool_2"
        description = "Second tool"
        def execute(self, input_data: str, context=None) -> str:
            return "ok2"

    registry.register(CustomTool1())
    agent = Agent(name="worker", role="Worker", tool_registry=registry)
    assert agent.available_tools() == ["custom_tool_1"]

    registry.register(CustomTool2())
    assert agent.available_tools() == ["custom_tool_1", "custom_tool_2"]


def test_team_builds_agents_with_actual_runtime_tools(tmp_path: Path):
    """Team._build_agents registers filesystem, knowledge, and web search tools correctly."""
    ws = Workspace.get_or_init(tmp_path, "Tools WS")
    sandbox = ws.sandbox
    knowledge = KnowledgeStore(db_path=str(tmp_path / "k.db"))

    agent_cfg = AgentConfig(
        name="full-agent",
        role="Specialist",
        tools=["filesystem", "search_knowledge", "search_web"],
    )
    team_cfg = TeamConfig(name="tool-team", agents=[agent_cfg])
    team = Team(team_cfg, sandbox=sandbox, knowledge_store=knowledge)

    built_agent = team.get_agent("full-agent")
    assert built_agent is not None

    available = built_agent.available_tools()
    assert "search_knowledge" in available
    assert "search_web" in available
    assert "list_directory" in available
    assert "read_file" in available
    assert "write_file" in available
    assert "patch_file"
    assert "delete_file" in available


@pytest.mark.asyncio
async def test_api_agent_and_workspace_tools_exposure(tmp_path: Path):
    """GET /agents and GET /workspace expose available tools and tool_count for each agent."""
    ws = Workspace.get_or_init(tmp_path, "Exposure WS")
    PresetApplier().apply_preset("developer-workforce", ws, set_as_default=True)
    app.state.workspace = ws
    app.state.team = ws.load_team()

    req = Request({"type": "http", "app": app})

    # Test GET /agents
    agents_list = await get_agents(req)
    assert len(agents_list) > 0
    for a in agents_list:
        assert "tools" in a
        assert "tool_count" in a
        assert isinstance(a["tools"], list)
        assert a["tool_count"] == len(a["tools"])

    # Test GET /workspace
    ws_info = await get_workspace(req)
    assert len(ws_info.agents) > 0
    for a in ws_info.agents:
        assert "tools" in a
        assert "tool_count" in a
        assert isinstance(a["tools"], list)
        assert a["tool_count"] == len(a["tools"])


@pytest.mark.asyncio
async def test_api_create_and_update_agent_with_custom_tools(tmp_path: Path):
    """POST /agents and PUT /agents accept tools list and persist them."""
    ws = Workspace.get_or_init(tmp_path, "Custom Agent Tools WS")
    PresetApplier().apply_preset("starter-workforce", ws, set_as_default=True)
    app.state.workspace = ws
    app.state.team = ws.load_team()

    req = Request({"type": "http", "app": app})

    # 1. Create agent with specific tools
    create_payload = AgentPayload(
        name="web-researcher",
        role="Web Specialist",
        instructions="Search the web and read files",
        icon="Search",
        color="cyan",
        tools=["search_web", "read_file"],
        skills=[],
        delegates_to=[],
    )
    res = await create_agent(req, create_payload)
    assert res == {"status": "ok"}

    # Verify agent
    agents_after = await get_agents(req)
    new_agent = next(a for a in agents_after if a["name"] == "web-researcher")
    assert "search_web" in new_agent["tools"]

    # 2. Update agent tools
    update_payload = AgentPayload(
        name="web-researcher",
        role="Senior Web Specialist",
        instructions="Search the web and read files",
        icon="Search",
        color="cyan",
        tools=["search_web", "list_directory", "read_file"],
        skills=[],
        delegates_to=[],
    )
    update_res = await update_agent(req, "web-researcher", update_payload)
    assert update_res == {"status": "ok"}

    agents_updated = await get_agents(req)
    updated_agent = next(a for a in agents_updated if a["name"] == "web-researcher")
    assert "list_directory" in updated_agent["tools"]


# ==============================================================================
# 3. Integration Tests (Slash commands & Legacy Compatibility)
# ==============================================================================

@pytest.mark.asyncio
async def test_slash_command_tools_uses_runtime_source_of_truth():
    """The /tools slash command reflects all tools registered in active agents."""
    reg = ToolRegistry()

    class AlphaTool(Tool):
        name = "alpha_tool"
        description = "Alpha tool description"
        def execute(self, input_data: str, context=None) -> str:
            return "alpha"

    reg.register(AlphaTool())
    agent = Agent(name="specialist", role="Specialist", tool_registry=reg)
    team = Team(TeamConfig(name="alpha-team", agents=[AgentConfig(name="specialist", role="Specialist")]))
    team._agents = {"specialist": agent}

    dispatcher = get_default_command_dispatcher()
    ctx = CommandContext(
        command="tools",
        args=[],
        raw_args="",
        team=team,
    )

    result = await dispatcher.dispatch("/tools", ctx)
    assert result.success is True
    assert "alpha_tool" in result.output
    assert any(t["name"] == "alpha_tool" for t in result.data["tools"])


@pytest.mark.asyncio
async def test_slash_command_status_includes_provider_health(tmp_path: Path):
    """The /status slash command includes live provider status and indicators."""
    ws = Workspace.get_or_init(tmp_path, "Slash Status WS")
    team = Team(TeamConfig(name="mock-team", default_provider="mock", default_model="test-model"))

    dispatcher = get_default_command_dispatcher()
    ctx = CommandContext(
        command="status",
        args=[],
        raw_args="",
        workspace=ws,
        team=team,
    )

    result = await dispatcher.dispatch("/status", ctx)
    assert result.success is True
    assert "Active Provider" in result.output
    assert "mock" in result.output
    assert "Connected" in result.output
    assert result.data.get("provider_status") is not None
    assert result.data["provider_status"]["reachable"] is True


def test_legacy_team_yaml_compatibility(tmp_path: Path):
    """Legacy team.yaml without tools/identity loads cleanly and serializes correctly."""
    legacy_yaml = """
team:
  name: legacy-workforce
  default_provider: ollama
  default_model: llama3

agents:
  - name: lead
    role: Lead
    relationships:
      - delegates_to: dev
  - name: dev
    role: Developer
"""
    f = tmp_path / "legacy.yaml"
    f.write_text(legacy_yaml, encoding="utf-8")

    config = TeamLoader.from_yaml(f)
    assert len(config.agents) == 2
    for a in config.agents:
        assert a.tools == []
        assert a.icon is None
        assert a.color is None

    serialized = TeamLoader.to_yaml_str(config)
    assert "legacy-workforce" in serialized
