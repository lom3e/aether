"""
Tests for Model Propagation, Inheritance vs Explicit Overrides, and Team Model Changes.

Validates the full specification:
1. Strict semantic distinction:
   - model = None / null -> Inherit from Team (dynamic fallback to team default_model)
   - model = "model_name" -> Explicit override (even if matching team default_model)
2. Exact test scenario:
   - Team = 9b
   - Agent A = Inherit (model=None)
   - Agent B = Override 0.8b (model="qwen3.5:0.8b")
   - Change Team -> 14b with "Solo Team" (apply_to_all_agents=False)
     => A becomes 14b, B remains 0.8b
   - Change Team -> 9b with "Applica a tutti" (apply_to_all_agents=True)
     => A and B both become inherited (model=None) and run 9b
3. Coincidental override ("qwen3.5:9b" on agent when team is 9b) remains unchanged when team changes to 14b with "Solo Team".
4. YAML persistence:
   - Inheriting agents do not write "model" in YAML
   - Overridden agents write "model: <name>" in YAML
5. Slash command /model <name> and /model <name> --all
6. Auto-Architect generates workforce in 100% inherited mode
"""
import pytest
from pathlib import Path
from starlette.requests import Request

from aether.workspace.workspace import Workspace
from aether.presets.applier import PresetApplier
from aether.team.team import Team
from aether.team.loader import TeamLoader
from aether.team.config import TeamConfig, AgentConfig
from aether.commands import CommandContext, get_default_command_dispatcher
from aether.server.routes import (
    apply_architect_workforce,
    ApplyArchitectWorkforcePayload,
    update_team,
    TeamPayload,
    AgentPayload,
)
from aether.providers.ollama import OllamaProvider


@pytest.fixture
def workspace_fixture(tmp_path):
    ws_dir = tmp_path / "model_prop_ws"
    ws = Workspace.init(ws_dir, name="Model Propagation Workspace")
    PresetApplier().apply_preset("developer-workforce", ws)
    return ws


def test_model_inheritance_and_override_scenario():
    """
    Validates the exact 7-step scenario:
    1. Team = 9b
    2. Agent A = Inherit (model=None)
    3. Agent B = Override 0.8b (model="qwen3.5:0.8b")
    4. Change Team -> 14b with 'Solo Team' (apply_to_all_agents=False)
       => A becomes 14b, B remains 0.8b
    5. Change Team -> 9b with 'Applica a tutti' (apply_to_all_agents=True)
       => A and B become both inherited from Team
    """
    # 1, 2, 3: Create Team = 9b, Agent A = Inherit, Agent B = Override 0.8b
    cfg = TeamConfig(
        name="DynamicSquad",
        default_provider="ollama",
        default_model="qwen3.5:9b",
        agents=[
            AgentConfig(name="AgentA", role="Inheriting Agent", model=None),
            AgentConfig(name="AgentB", role="Overridden Agent", model="qwen3.5:0.8b"),
        ],
    )
    team = Team(config=cfg)

    # Initial state verification
    assert team.config.default_model == "qwen3.5:9b"
    agent_a = team.get_agent("AgentA")
    agent_b = team.get_agent("AgentB")
    assert agent_a.config.model is None
    assert agent_a.provider._model == "qwen3.5:9b"
    assert agent_b.config.model == "qwen3.5:0.8b"
    assert agent_b.provider._model == "qwen3.5:0.8b"

    # 4. Change Team -> 14b with "Solo Team" (apply_to_all_agents=False)
    team.set_model("qwen3.5:14b", apply_to_all_agents=False)
    assert team.config.default_model == "qwen3.5:14b"
    # Agent A follows team -> 14b
    assert agent_a.config.model is None
    assert agent_a.provider._model == "qwen3.5:14b"
    # Agent B retains explicit override -> 0.8b
    assert agent_b.config.model == "qwen3.5:0.8b"
    assert agent_b.provider._model == "qwen3.5:0.8b"

    # 5. Change Team -> 9b with "Applica a tutti" (apply_to_all_agents=True)
    team.set_model("qwen3.5:9b", apply_to_all_agents=True)
    assert team.config.default_model == "qwen3.5:9b"
    # Both agents are now inheriting (model=None) and running 9b
    assert agent_a.config.model is None
    assert agent_a.provider._model == "qwen3.5:9b"
    assert agent_b.config.model is None
    assert agent_b.provider._model == "qwen3.5:9b"


def test_coincidental_override_remains_intact():
    """
    Verifies that if an agent has model="qwen3.5:9b" explicitly (even when the team
    is also 9b), it is treated as an explicit override and does NOT change when
    team model changes with apply_to_all_agents=False.
    """
    cfg = TeamConfig(
        name="OverrideSquad",
        default_provider="ollama",
        default_model="qwen3.5:9b",
        agents=[
            AgentConfig(name="Inheritor", role="Follows Team", model=None),
            AgentConfig(name="ExplicitNineB", role="Pinned to 9b", model="qwen3.5:9b"),
        ],
    )
    team = Team(config=cfg)

    # Initial state
    assert team.get_agent("Inheritor").config.model is None
    assert team.get_agent("ExplicitNineB").config.model == "qwen3.5:9b"

    # Team changes to 14b (Solo Team)
    team.set_model("qwen3.5:14b", apply_to_all_agents=False)

    # Inheritor follows to 14b, ExplicitNineB remains pinned to 9b
    assert team.get_agent("Inheritor").config.model is None
    assert team.get_agent("Inheritor").provider._model == "qwen3.5:14b"
    assert team.get_agent("ExplicitNineB").config.model == "qwen3.5:9b"
    assert team.get_agent("ExplicitNineB").provider._model == "qwen3.5:9b"


def test_yaml_serialization_strict_null_vs_string(tmp_path):
    """
    Verifies that TeamLoader omits 'model' key for inherited agents, writes 'model: ...'
    for overridden agents, and faithfully restores both on deserialization.
    """
    cfg = TeamConfig(
        name="YamlSquad",
        default_provider="ollama",
        default_model="qwen3.5:9b",
        agents=[
            AgentConfig(name="AgentInherit", role="Researcher", model=None),
            AgentConfig(name="AgentCustom", role="Coder", model="qwen3.5:0.8b"),
        ],
    )
    yaml_file = tmp_path / "test_team.yaml"
    TeamLoader.to_yaml(cfg, yaml_file)

    yaml_text = yaml_file.read_text(encoding="utf-8")
    assert "AgentInherit" in yaml_text
    assert "AgentCustom" in yaml_text
    assert "qwen3.5:0.8b" in yaml_text

    # Reload from disk
    reloaded = TeamLoader.from_yaml(yaml_file)
    assert reloaded.default_model == "qwen3.5:9b"

    agent_inherit = next(a for a in reloaded.agents if a.name == "AgentInherit")
    agent_custom = next(a for a in reloaded.agents if a.name == "AgentCustom")

    assert agent_inherit.model is None
    assert agent_custom.model == "qwen3.5:0.8b"


@pytest.mark.asyncio
async def test_slash_model_with_all_flag(workspace_fixture):
    """
    Verifies /model <name> preserves overrides and /model <name> --all clears overrides.
    """
    ws = workspace_fixture
    team = ws.load_team("developer-workforce")
    team.config.agents[0].model = None
    team.config.agents[1].model = "qwen3.5:0.8b"
    team.set_model("qwen3.5:9b", apply_to_all_agents=False)

    app_state = type("AppState", (), {
        "workspace": ws,
        "team": team,
        "active_team_name": "developer-workforce",
    })()

    dispatcher = get_default_command_dispatcher()
    cmd_ctx = CommandContext(
        command="model",
        args=["qwen3.5:14b"],
        raw_args="qwen3.5:14b",
        workspace=ws,
        team=team,
        conversation_id="test-conv",
        session_id="test-conv",
        app_state=app_state,
    )

    # 1. /model qwen3.5:14b (without --all) -> Preserves Agent[1] override
    res1 = await dispatcher.dispatch("/model qwen3.5:14b", cmd_ctx)
    assert res1.success is True
    assert "14b" in res1.output
    assert team.config.agents[0].model is None
    assert team.config.agents[0].name in team._agents
    assert team.get_agent(team.config.agents[0].name).provider._model == "qwen3.5:14b"
    assert team.config.agents[1].model == "qwen3.5:0.8b"
    assert team.get_agent(team.config.agents[1].name).provider._model == "qwen3.5:0.8b"

    # 2. /model qwen3.5:9b --all -> Clears overrides
    cmd_ctx_all = CommandContext(
        command="model",
        args=["qwen3.5:9b", "--all"],
        raw_args="qwen3.5:9b --all",
        workspace=ws,
        team=team,
        conversation_id="test-conv",
        session_id="test-conv",
        app_state=app_state,
    )
    res2 = await dispatcher.dispatch("/model qwen3.5:9b --all", cmd_ctx_all)
    assert res2.success is True
    assert "qwen3.5:9b" in res2.output
    assert team.config.agents[0].model is None
    assert team.get_agent(team.config.agents[0].name).provider._model == "qwen3.5:9b"
    assert team.config.agents[1].model is None
    assert team.get_agent(team.config.agents[1].name).provider._model == "qwen3.5:9b"


@pytest.mark.asyncio
async def test_api_update_team_apply_to_all(tmp_path):
    """
    Tests REST endpoint PUT /api/teams/{team_name} with apply_to_all_agents=True / False.
    """
    ws_dir = tmp_path / "api_team_ws"
    ws = Workspace.init(ws_dir, name="API Team Workspace")
    PresetApplier().apply_preset("developer-workforce", ws)

    class DummyAppState:
        workspace = ws
        team = ws.load_team("developer-workforce")
        active_team_name = "developer-workforce"

    class DummyApp:
        state = DummyAppState()

    req = Request(scope={"type": "http", "app": DummyApp()})

    # Update with 1 override and apply_to_all_agents=False
    payload_mixed = TeamPayload(
        name="developer-workforce",
        default_provider="ollama",
        default_model="qwen3.5:14b",
        apply_to_all_agents=False,
        agents=[
            AgentPayload(name="Lead", role="Lead Dev", model=None, provider=None),
            AgentPayload(name="Coder", role="Coder", model="qwen3.5:0.8b", provider="ollama"),
        ],
    )
    res1 = await update_team(req, "developer-workforce", payload_mixed)
    assert res1["status"] == "ok"

    updated_team = ws.load_team("developer-workforce")
    assert updated_team.config.default_model == "qwen3.5:14b"
    lead = updated_team.get_agent("Lead")
    coder = updated_team.get_agent("Coder")
    assert lead.config.model is None
    assert lead.provider._model == "qwen3.5:14b"
    assert coder.config.model == "qwen3.5:0.8b"
    assert coder.provider._model == "qwen3.5:0.8b"

    # Update with apply_to_all_agents=True -> clears coder override
    payload_all = TeamPayload(
        name="developer-workforce",
        default_provider="ollama",
        default_model="qwen3.5:9b",
        apply_to_all_agents=True,
        agents=[
            AgentPayload(name="Lead", role="Lead Dev", model=None, provider=None),
            AgentPayload(name="Coder", role="Coder", model="qwen3.5:0.8b", provider="ollama"),
        ],
    )
    res2 = await update_team(req, "developer-workforce", payload_all)
    assert res2["status"] == "ok"

    unfied_team = ws.load_team("developer-workforce")
    assert unfied_team.config.default_model == "qwen3.5:9b"
    for agent in unfied_team.agents():
        assert agent.config.model is None
        assert agent.provider._model == "qwen3.5:9b"


@pytest.mark.asyncio
async def test_auto_architect_created_team_model_inheritance(tmp_path):
    """Verify team created by Auto-Architect inherits model updates seamlessly."""
    ws_dir = tmp_path / "arch_prop_ws"
    ws = Workspace.init(ws_dir, name="Arch Propagation")

    class DummyAppState:
        workspace = ws
        team = None

    class DummyApp:
        state = DummyAppState()

    req = Request(scope={"type": "http", "app": DummyApp()})

    payload = ApplyArchitectWorkforcePayload(
        team_name="Market Intelligence",
        description="Market research squad",
        icon="Compass",
        color="violet",
        default_provider="ollama",
        default_model="qwen3.5:0.8b",
        agents=[
            {
                "name": "Market Lead",
                "role": "Coordinator",
                "system_prompt": "You coordinate market analysis.",
                "icon": "Compass",
                "color": "violet",
                "delegates_to": ["Data Scraper"],
                "skills": ["search_knowledge"],
            },
            {
                "name": "Data Scraper",
                "role": "Scraper Specialist",
                "system_prompt": "You collect competitor data.",
                "icon": "Search",
                "color": "cyan",
                "delegates_to": [],
                "skills": ["search_knowledge"],
            },
        ],
    )

    res = await apply_architect_workforce(req, payload)
    assert res["status"] == "ok"

    team = ws.load_team("Market Intelligence")
    assert team.config.default_model == "qwen3.5:0.8b"
    for agent in team.agents():
        assert agent.config.model is None
        assert agent.provider._model == "qwen3.5:0.8b"

    # Now change model to 9b
    team.set_model("qwen3.5:9b")
    assert team.config.default_model == "qwen3.5:9b"
    for agent in team.agents():
        assert agent.config.model is None
        assert agent.provider._model == "qwen3.5:9b"
