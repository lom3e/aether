"""
test_agent_identity_phase10.py

Tests for P1-05: Agent & Workforce Identity (icon, color, AgentConfig, runtime, presets, API).
"""
import pytest
from pathlib import Path

from aether.team.config import (
    AgentConfig,
    Relationship,
    TeamConfig,
    SUPPORTED_AGENT_COLORS,
    SUPPORTED_AGENT_ICONS,
)
from aether.team.loader import TeamLoader
from aether.agents.agent import Agent
from aether.team.team import Team
from aether.presets.loader import PresetLoader
from aether.server.app import app
from aether.workspace.workspace import Workspace
from aether.commands.models import CommandContext
from aether.commands.dispatcher import get_default_command_dispatcher


def test_agent_config_identity_fields():
    """Test that AgentConfig accepts icon and color, defaulting to None."""
    agent_default = AgentConfig(name="worker", role="Worker")
    assert agent_default.icon is None
    assert agent_default.color is None

    agent_custom = AgentConfig(
        name="coder",
        role="Developer",
        icon="Code",
        color="blue",
    )
    assert agent_custom.icon == "Code"
    assert agent_custom.color == "blue"
    d = agent_custom.to_dict()
    assert d["icon"] == "Code"
    assert d["color"] == "blue"
    assert "Code" in repr(agent_custom)
    assert "blue" in repr(agent_custom)


def test_supported_constants():
    """Verify supported palette and icon definitions."""
    assert "violet" in SUPPORTED_AGENT_COLORS
    assert "blue" in SUPPORTED_AGENT_COLORS
    assert "emerald" in SUPPORTED_AGENT_COLORS
    assert "Code" in SUPPORTED_AGENT_ICONS
    assert "Search" in SUPPORTED_AGENT_ICONS
    assert "Bot" in SUPPORTED_AGENT_ICONS


def test_team_loader_yaml_with_identity(tmp_path: Path):
    """Test that TeamLoader parses icon and color from YAML and serializes them back."""
    yaml_content = """
team:
  name: identity-team
  provider: ollama
  model: llama3.2

agents:
  - name: architect
    role: Lead Architect
    icon: Compass
    color: violet
    relationships:
      - delegates_to: coder

  - name: coder
    role: Software Engineer
    icon: Code
    color: blue
"""
    yaml_file = tmp_path / "team.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    config = TeamLoader.from_yaml(yaml_file)
    assert len(config.agents) == 2

    architect = config.get_agent("architect")
    assert architect is not None
    assert architect.icon == "Compass"
    assert architect.color == "violet"

    coder = config.get_agent("coder")
    assert coder is not None
    assert coder.icon == "Code"
    assert coder.color == "blue"

    # Test serialization back to YAML
    serialized = TeamLoader.to_yaml_str(config)
    assert "icon: Compass" in serialized
    assert "color: violet" in serialized
    assert "icon: Code" in serialized
    assert "color: blue" in serialized

    # Reload from serialized
    import yaml
    reloaded = TeamLoader.from_dict(yaml.safe_load(serialized))
    assert reloaded.get_agent("architect").icon == "Compass"
    assert reloaded.get_agent("coder").color == "blue"


def test_team_loader_backward_compatibility(tmp_path: Path):
    """Legacy team.yaml without icon/color must load cleanly with None values."""
    legacy_yaml = """
team:
  name: legacy-team

agents:
  - name: coordinator
    role: Coordinator
    relationships:
      - delegates_to: assistant
  - name: assistant
    role: Assistant
"""
    yaml_file = tmp_path / "legacy.yaml"
    yaml_file.write_text(legacy_yaml, encoding="utf-8")

    config = TeamLoader.from_yaml(yaml_file)
    for agent in config.agents:
        assert agent.icon is None
        assert agent.color is None

    serialized = TeamLoader.to_yaml_str(config)
    assert "icon:" not in serialized
    assert "color:" not in serialized


def test_runtime_agent_identity_propagation():
    """Verify that Team._build_agents propagates icon and color to Agent runtime instances."""
    agent_cfg1 = AgentConfig(name="manager", role="Manager", icon="Bot", color="violet")
    agent_cfg2 = AgentConfig(name="dev", role="Developer", icon="Code", color="emerald")
    team_cfg = TeamConfig(name="test-team", agents=[agent_cfg1, agent_cfg2])

    team = Team(team_cfg)
    agents = team.agents()
    assert len(agents) == 2

    manager_agent = next(a for a in agents if a.name == "manager")
    assert manager_agent.icon == "Bot"
    assert manager_agent.color == "violet"
    assert manager_agent.config == agent_cfg1

    dev_agent = next(a for a in agents if a.name == "dev")
    assert dev_agent.icon == "Code"
    assert dev_agent.color == "emerald"
    assert dev_agent.config == agent_cfg2


def test_builtin_presets_have_identity():
    """Verify that all builtin presets define semantic icons and colors for their agents."""
    loader = PresetLoader()
    presets = loader.list_presets()
    assert len(presets) >= 4

    preset_ids = {p.id for p in presets}
    assert "developer-workforce" in preset_ids
    assert "research-workforce" in preset_ids
    assert "starter-workforce" in preset_ids
    assert "business-operations-workforce" in preset_ids

    # Inspect Developer Workforce
    dev_preset, _ = loader.get_preset("developer-workforce")
    dev_agents = {a.name: a for a in dev_preset.agents}
    assert dev_agents["development-manager"].icon == "Compass"
    assert dev_agents["development-manager"].color == "violet"
    assert dev_agents["code-analyst"].icon == "Code"
    assert dev_agents["code-analyst"].color == "blue"
    assert dev_agents["code-reviewer"].icon == "ShieldCheck"
    assert dev_agents["code-reviewer"].color == "emerald"
    assert dev_agents["documentation-writer"].icon == "PenTool"
    assert dev_agents["documentation-writer"].color == "amber"

    # Inspect Research Workforce
    res_preset, _ = loader.get_preset("research-workforce")
    res_agents = {a.name: a for a in res_preset.agents}
    assert res_agents["research-manager"].icon == "Brain"
    assert res_agents["researcher"].icon == "Search"
    assert res_agents["analyst"].icon == "Database"


@pytest.mark.asyncio
async def test_api_agent_identity_endpoints(tmp_path: Path):
    """Test GET /agents, GET /workspace, POST /agents, and PUT /agents with identity fields."""
    from starlette.requests import Request
    from aether.server.routes import get_agents, get_workspace, create_agent, update_agent, AgentPayload
    from aether.presets.applier import PresetApplier

    ws = Workspace.get_or_init(tmp_path, "Identity Workspace")
    PresetApplier().apply_preset("starter-workforce", ws, set_as_default=True)
    app.state.workspace = ws
    app.state.team = ws.load_team()

    def _make_req():
        req = Request({"type": "http", "app": app})
        return req

    # 1. Check initial agents from default preset
    req = _make_req()
    agents = await get_agents(req)
    assert len(agents) > 0
    # Every preset agent has an icon and color
    for a in agents:
        assert "icon" in a
        assert "color" in a

    # 2. Check GET /workspace
    ws_info = await get_workspace(req)
    assert len(ws_info.agents) > 0
    for a in ws_info.agents:
        assert "icon" in a
        assert "color" in a

    # 3. Create a new agent with icon and color
    create_payload = AgentPayload(
        name="security-officer",
        role="Security Specialist",
        instructions="Inspect security vulnerabilities",
        icon="ShieldCheck",
        color="rose",
        skills=[],
        delegates_to=[],
    )
    create_res = await create_agent(req, create_payload)
    assert create_res == {"status": "ok"}

    # Verify created agent
    agents_after_create = await get_agents(req)
    new_agent = next(a for a in agents_after_create if a["name"] == "security-officer")
    assert new_agent["icon"] == "ShieldCheck"
    assert new_agent["color"] == "rose"

    # 4. Update the agent's identity
    update_payload = AgentPayload(
        name="security-officer",
        role="Lead Security Architect",
        instructions="Inspect security vulnerabilities",
        icon="Zap",
        color="cyan",
        skills=[],
        delegates_to=[],
    )
    update_res = await update_agent(req, "security-officer", update_payload)
    assert update_res == {"status": "ok"}

    # Verify updated agent
    agents_after_update = await get_agents(req)
    updated_agent = next(a for a in agents_after_update if a["name"] == "security-officer")
    assert updated_agent["role"] == "Lead Security Architect"
    assert updated_agent["icon"] == "Zap"
    assert updated_agent["color"] == "cyan"


@pytest.mark.asyncio
async def test_slash_command_agents_displays_identity(tmp_path: Path):
    """Test that /agents slash command includes icon and color in its output and data payload."""
    agent1 = AgentConfig(name="lead", role="Lead", icon="Compass", color="violet")
    agent2 = AgentConfig(name="scout", role="Scout", icon="Search", color="cyan")
    team = Team(TeamConfig(name="scout-team", agents=[agent1, agent2]))

    dispatcher = get_default_command_dispatcher()
    ctx = CommandContext(
        command="agents",
        args=[],
        raw_args="",
        team=team,
    )

    result = await dispatcher.dispatch("/agents", ctx)
    assert result.success is True
    assert "icon: `Compass`" in result.output
    assert "color: `violet`" in result.output
    assert "icon: `Search`" in result.output
    assert "color: `cyan`" in result.output
    assert result.data["agents"][0]["icon"] == "Compass"
    assert result.data["agents"][0]["color"] == "violet"
