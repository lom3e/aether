import pytest
from aether.intelligence.architect import (
    build_heuristic_workforce,
    generate_workforce_architecture,
    enhance_system_prompt,
    build_heuristic_enhanced_prompt,
)
from aether.providers.mock import MockProvider


def test_heuristic_workforce_ecommerce():
    wf = build_heuristic_workforce("Voglio monitorare i competitor, estrarre prezzi e ricevere un report settimanale")
    assert wf.team_name == "Market & Competitor Intelligence"
    assert len(wf.agents) >= 3
    assert wf.entry_agent == "Intelligence Lead"
    assert any("web_search" in a.skills for a in wf.agents)


def test_heuristic_workforce_code():
    wf = build_heuristic_workforce("Voglio automatizzare la code review e creare test automatici per le API python")
    assert wf.team_name == "Full-Stack Engineering & QA"
    assert len(wf.agents) == 3
    assert wf.entry_agent == "Tech Lead"
    assert any("QA" in a.name or "Test" in a.name for a in wf.agents)


def test_heuristic_workforce_finance():
    wf = build_heuristic_workforce("Analisi di bilancio aziendale, KPI di cassa e compliance fiscale")
    assert wf.team_name == "Financial & Operations Intelligence"
    assert len(wf.agents) == 3
    assert wf.entry_agent == "Finance Director"


def test_heuristic_workforce_generic_custom():
    wf = build_heuristic_workforce("Gestione logistica delle spedizioni marittime internazionali")
    assert "Squad" in wf.team_name or "Strategic" in wf.team_name
    assert len(wf.agents) >= 2


@pytest.mark.asyncio
async def test_generate_workforce_with_mock_provider():
    mock_json = """{
        "team_name": "AI Growth Squad",
        "description": "Marketing and acquisition team",
        "icon": "Zap",
        "color": "emerald",
        "entry_agent": "Growth Lead",
        "suggested_starter_tasks": ["Launch campaign"],
        "agents": [
            {
                "name": "Growth Lead",
                "role": "Orchestrator",
                "icon": "Zap",
                "color": "emerald",
                "delegates_to": ["SEO Analyst"],
                "skills": ["web_search"],
                "system_prompt": "You lead the growth squad."
            },
            {
                "name": "SEO Analyst",
                "role": "Search Specialist",
                "icon": "Search",
                "color": "cyan",
                "delegates_to": [],
                "skills": ["web_search"],
                "system_prompt": "You analyze keywords."
            }
        ]
    }"""
    provider = MockProvider(responses=[mock_json])
    blueprint = await generate_workforce_architecture("Scale user acquisition", provider=provider)
    assert blueprint.team_name == "AI Growth Squad"
    assert blueprint.generation_source == "ai"
    assert len(blueprint.agents) == 2
    assert blueprint.agents[0].name == "Growth Lead"
    assert blueprint.agents[0].delegates_to == ["SEO Analyst"]


@pytest.mark.asyncio
async def test_generate_workforce_provider_fallback_on_invalid_json():
    provider = MockProvider(responses=["Sorry, I cannot produce JSON right now."])
    blueprint = await generate_workforce_architecture("Analisi competitor e prezzi", provider=provider)
    assert blueprint.generation_source == "heuristic"
    assert blueprint.team_name == "Market & Competitor Intelligence"


def test_enhance_prompt_heuristic():
    enhanced = build_heuristic_enhanced_prompt(
        raw_prompt="esperto seo e copywriting",
        role="SEO Writer",
        agent_name="Ghostwriter",
        team_name="Content Team"
    )
    assert "Ghostwriter" in enhanced
    assert "SEO Writer" in enhanced
    assert "Primary Objective" in enhanced
    assert "Deliverable Format" in enhanced
    assert "Guardrails" in enhanced


@pytest.mark.asyncio
async def test_enhance_prompt_with_mock_provider():
    mock_enhanced = "## 🎯 Objective: Master SEO strategies with high precision."
    provider = MockProvider(responses=[mock_enhanced])
    result = await enhance_system_prompt("Scrivi articoli SEO", role="Writer", provider=provider)
    assert "Objective: Master SEO" in result


@pytest.mark.asyncio
async def test_apply_architect_workforce_persists_to_workspace(tmp_path):
    from aether.workspace.workspace import Workspace
    from aether.server.routes import apply_architect_workforce, ApplyArchitectWorkforcePayload
    from starlette.requests import Request

    ws_dir = tmp_path / "test-arch-ws"
    ws = Workspace.init(ws_dir, name="Architect Test Workspace")

    class DummyAppState:
        workspace = ws
        team = None

    class DummyApp:
        state = DummyAppState()

    req = Request(scope={"type": "http", "app": DummyApp()})

    payload = ApplyArchitectWorkforcePayload(
        team_name="Cybersecurity Red Team",
        description="Vulnerability assessment and pentesting squad",
        icon="ShieldCheck",
        color="rose",
        agents=[
            {
                "name": "Sec Lead",
                "role": "Red Team Coordinator",
                "system_prompt": "You coordinate pentests.",
                "icon": "ShieldCheck",
                "color": "rose",
                "delegates_to": ["Scanner Specialist"],
                "skills": ["terminal_sandbox"],
            },
            {
                "name": "Scanner Specialist",
                "role": "Port & Vuln Scanner",
                "system_prompt": "You run security audits.",
                "icon": "Terminal",
                "color": "amber",
                "delegates_to": [],
                "skills": ["terminal_sandbox"],
            },
        ],
    )

    res = await apply_architect_workforce(req, payload)
    assert res["status"] == "ok"
    assert res["team"]["name"] == "Cybersecurity Red Team"
    assert res["team"]["agent_count"] == 2

    # Verify team file exists and can be loaded
    team = ws.load_team("Cybersecurity Red Team")
    assert team.config.name == "Cybersecurity Red Team"
    assert len(team.agents()) == 2
    assert "Sec Lead" in [a.name for a in team.agents()]
    assert "Scanner Specialist" in [a.name for a in team.agents()]
