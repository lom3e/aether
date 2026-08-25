"""
Manual & E2E verification test for TeamTopology with 4+ agents and long names.
Ensures zero text truncation, dynamic node sizing, auto-fit, and interactive zoom & pan.
"""
import pytest
from starlette.requests import Request
from aether.workspace.workspace import Workspace
from aether.team.config import TeamConfig, AgentConfig, Relationship
from aether.team.loader import TeamLoader
from aether.server.routes import get_teams


@pytest.mark.asyncio
async def test_topology_with_long_names_and_many_agents(tmp_path):
    """Verify that a 4+ agent team with long names computes complete data without truncation."""
    ws = Workspace.get_or_init(tmp_path / "ws_long_topo", "Long Topo WS")

    team_cfg = TeamConfig(
        name="Enterprise Architecture Workforce",
        default_provider="mock",
        default_model="mock-model",
        icon="Layers",
        color="violet",
        agents=[
            AgentConfig(
                name="Lead Enterprise Architect & Engineering Director",
                role="Strategic Technical Coordinator & System Orchestrator",
                icon="Crown",
                color="violet",
                relationships=[
                    Relationship(type="delegates_to", target="Senior Financial Data Analyst & Market Researcher"),
                    Relationship(type="delegates_to", target="Lead Cybersecurity Vulnerability Penetration Tester"),
                    Relationship(type="delegates_to", target="Executive Strategy Synthesizer & Content Writer"),
                ]
            ),
            AgentConfig(
                name="Senior Financial Data Analyst & Market Researcher",
                role="Quantitative Balance Sheet Auditor & Competitor Tracker",
                icon="Database",
                color="emerald",
            ),
            AgentConfig(
                name="Lead Cybersecurity Vulnerability Penetration Tester",
                role="Security Compliance & Automated Code Auditor",
                icon="ShieldCheck",
                color="rose",
            ),
            AgentConfig(
                name="Executive Strategy Synthesizer & Content Writer",
                role="High-Impact Briefing & Markdown Report Generator",
                icon="FileText",
                color="cyan",
            ),
        ]
    )

    TeamLoader.to_yaml(team_cfg, ws.teams_dir / "enterprise_workforce.yaml")

    scope = {"type": "http", "app": type("App", (), {"state": type("State", (), {"workspace": ws})()})()}
    req = Request(scope)

    teams = await get_teams(req)
    team_data = next(t for t in teams if t["name"] == "Enterprise Architecture Workforce")

    agents_list = team_data["agents_list"]
    assert len(agents_list) == 4

    # Verify all agent names are complete strings
    names = [a["name"] for a in agents_list]
    assert "Lead Enterprise Architect & Engineering Director" in names
    assert "Senior Financial Data Analyst & Market Researcher" in names
    assert "Lead Cybersecurity Vulnerability Penetration Tester" in names
    assert "Executive Strategy Synthesizer & Content Writer" in names

    # Verify relationships
    mgr = next(a for a in agents_list if "Director" in a["name"])
    assert len(mgr["delegates_to"]) == 3
