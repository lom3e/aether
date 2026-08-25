"""
Tests for Team Deletion and Agent System Prompt / Instructions Persistence.
"""
import pytest
from starlette.requests import Request
from starlette.exceptions import HTTPException

from aether.workspace.workspace import Workspace
from aether.presets.applier import PresetApplier
from aether.team.loader import TeamLoader
from aether.team.config import TeamConfig, AgentConfig
from aether.server.routes import (
    get_agents,
    update_agent,
    delete_team,
    AgentPayload,
)


@pytest.mark.asyncio
async def test_team_deletion_lifecycle(tmp_path):
    """Verify delete_team removes YAML, handles active team switch, and prevents deleting last team."""
    ws = Workspace.init(tmp_path / "team_del_ws", name="Team Deletion Workspace")
    PresetApplier().apply_preset("starter-workforce", ws)
    PresetApplier().apply_preset("developer-workforce", ws)

    # We now have 2 teams
    team1 = ws.load_team("starter-workforce")

    class DummyAppState:
        workspace = ws
        team = team1
        active_team_name = "starter-workforce"

    class DummyApp:
        state = DummyAppState()

    req = Request(scope={"type": "http", "app": DummyApp()})

    # 1. Delete starter-workforce (active team)
    res = await delete_team(req, "starter-workforce")
    assert res["status"] == "ok"
    assert not (ws.teams_dir / "starter-workforce.yaml").exists()

    # Verify active team automatically switched to developer-workforce
    assert req.app.state.active_team_name == "developer-workforce"
    assert req.app.state.team.config.name == "developer-workforce"

    # 2. Attempt to delete developer-workforce (the only remaining team) -> should raise 400
    with pytest.raises(HTTPException) as exc_info:
        await delete_team(req, "developer-workforce")
    assert exc_info.value.status_code == 400
    assert "only team" in str(exc_info.value.detail)

    # 3. Attempt to delete non-existent team -> 404
    with pytest.raises(HTTPException) as exc_info_404:
        await delete_team(req, "non-existent-team")
    assert exc_info_404.value.status_code == 404


@pytest.mark.asyncio
async def test_agent_instructions_persistence(tmp_path):
    """Verify agent instructions/prompt are faithfully returned and persisted."""
    ws = Workspace.init(tmp_path / "agent_prompt_ws", name="Prompt Workspace")
    PresetApplier().apply_preset("starter-workforce", ws)
    team = ws.load_team("starter-workforce")

    app_state = type("AppState", (), {
        "workspace": ws,
        "team": team,
        "active_team_name": "starter-workforce",
    })()

    class DummyApp:
        state = app_state

    req = Request(scope={"type": "http", "app": DummyApp()})

    # 1. Initial agents fetch
    agents = await get_agents(req)
    assert len(agents) > 0
    first_agent_name = agents[0]["name"]

    # 2. Update agent with rich custom prompt
    custom_prompt = "You are an elite researcher specialized in deep-dive market analytics and competitor intelligence."
    payload = AgentPayload(
        name=first_agent_name,
        role="Senior Intelligence Specialist",
        instructions=custom_prompt,
        skills=["search_knowledge"],
        delegates_to=[],
    )
    update_res = await update_agent(req, first_agent_name, payload)
    assert update_res["status"] == "ok"

    # 3. Fetch agents again and verify prompt is returned in both instructions and description
    updated_agents = await get_agents(req)
    target = next(a for a in updated_agents if a["name"] == first_agent_name)
    assert target["instructions"] == custom_prompt
    assert target["description"] == custom_prompt


@pytest.mark.asyncio
async def test_generate_agent_draft_and_endpoint(tmp_path):
    """Verify AI Agent Drafting heuristic fallback and /api/architect/agent-draft endpoint."""
    ws = Workspace.init(tmp_path / "draft_ws", name="Draft Workspace")
    PresetApplier().apply_preset("starter-workforce", ws)
    team = ws.load_team("starter-workforce")

    from aether.intelligence.architect import generate_agent_draft, build_heuristic_agent_draft
    from aether.server.routes import generate_agent_draft_endpoint, AgentDraftPayload

    # 1. Deterministic heuristic drafting
    blueprint = build_heuristic_agent_draft("Voglio un analista per bilanci e dati finanziari")
    assert "Analyst" in blueprint.name
    assert blueprint.icon == "Database"
    assert blueprint.color == "emerald"
    assert "Objective" in blueprint.system_prompt

    # 2. Endpoint call
    app_state = type("AppState", (), {
        "workspace": ws,
        "team": team,
        "active_team_name": "starter-workforce",
    })()

    class DummyApp:
        state = app_state

    req = Request(scope={"type": "http", "app": DummyApp()})

    res = await generate_agent_draft_endpoint(
        req,
        AgentDraftPayload(
            goal="Voglio un esperto di cybersecurity per audit di codice",
            available_skills=["filesystem_tools", "search_knowledge"],
            available_agents=["Manager", "Researcher"],
        )
    )
    assert "name" in res
    assert "role" in res
    assert "system_prompt" in res
    assert res["icon"] in ["ShieldCheck", "Bot", "Cpu"]
    assert isinstance(res["skills"], list)


@pytest.mark.asyncio
async def test_apply_architect_workforce_model_preservation(tmp_path):
    """Verify applying architect workforce preserves explicit agent model overrides vs team inheritance."""
    ws = Workspace.init(tmp_path / "apply_ws", name="Apply Workspace")
    PresetApplier().apply_preset("starter-workforce", ws)
    team = ws.load_team("starter-workforce")

    from aether.server.routes import apply_architect_workforce, ApplyArchitectWorkforcePayload

    app_state = type("AppState", (), {
        "workspace": ws,
        "team": team,
        "active_team_name": "starter-workforce",
    })()

    class DummyApp:
        state = app_state

    req = Request(scope={"type": "http", "app": DummyApp()})

    payload = ApplyArchitectWorkforcePayload(
        team_name="custom-workforce",
        description="Custom AI team",
        default_provider="ollama",
        default_model="qwen3.5:9b",
        agents=[
            {
                "name": "AgentInherit",
                "role": "Generalist",
                "system_prompt": "Inherits team model",
                "icon": "Bot",
                "color": "violet",
                "delegates_to": ["AgentOverride"],
                "skills": ["search_knowledge"],
                "model": None, # Inherits
            },
            {
                "name": "AgentOverride",
                "role": "Fast Assistant",
                "system_prompt": "Explicit override",
                "icon": "Zap",
                "color": "cyan",
                "delegates_to": [],
                "skills": [],
                "model": "qwen3.5:0.8b", # Explicit override
            },
        ],
    )

    res = await apply_architect_workforce(req, payload)
    assert res["status"] == "ok"

    # Reload saved team config from YAML
    saved_team = ws.load_team("custom-workforce")
    assert saved_team.config.default_model == "qwen3.5:9b"
    agent_inherit = saved_team.config.get_agent("AgentInherit")
    assert agent_inherit.model is None # Must inherit

    agent_override = saved_team.config.get_agent("AgentOverride")
    assert agent_override.model == "qwen3.5:0.8b" # Explicit override preserved!
