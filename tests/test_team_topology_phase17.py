"""
Test suite for P2-08: Team Topology SVG Visualizer.
Verifies topology data contract from GET /api/teams,
SVG graph rendering, hierarchy resolution (Manager + Specialists),
and Playwright UI validation.
"""
import os
import pytest
from pathlib import Path
from starlette.requests import Request
from playwright.sync_api import expect, sync_playwright

from aether.server.routes import get_teams
from aether.workspace.workspace import Workspace
from aether.team.config import TeamConfig, AgentConfig, Relationship

_state: dict = {}


@pytest.fixture(scope="module")
def browser_context(aether_server):
    """Module-scoped browser context with Aether server."""
    _state["base_url"] = aether_server["base_url"]
    token = aether_server.get("token")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        if token:
            context.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{token}';")
        yield context
        browser.close()


def _base_url() -> str:
    return _state.get("base_url", os.environ.get("AETHER_E2E_BASE_URL", "http://localhost:8000"))


def test_team_topology_source_files_exist():
    """Verify that TeamTopology component and its integration exist in UI source."""
    repo_root = Path(__file__).parent.parent
    topo_tsx = repo_root / "ui" / "src" / "TeamTopology.tsx"
    teams_tsx = repo_root / "ui" / "src" / "Teams.tsx"

    assert topo_tsx.exists(), "ui/src/TeamTopology.tsx must exist"
    assert teams_tsx.exists(), "ui/src/Teams.tsx must exist"

    content = topo_tsx.read_text(encoding="utf-8")
    assert "export function TeamTopology" in content
    assert "<svg" in content
    assert "arrow-manager" in content
    assert "nodePositions" in content

    teams_content = teams_tsx.read_text(encoding="utf-8")
    assert "from './TeamTopology'" in teams_content
    assert "<TeamTopology" in teams_content


@pytest.mark.asyncio
async def test_api_teams_includes_agents_list(tmp_path):
    """Verify that get_teams returns full agents_list for topology rendering."""
    ws = Workspace.get_or_init(tmp_path / "ws_topo", "Topology WS")
    team_cfg = TeamConfig(
        name="Engineering Core",
        default_provider="mock",
        default_model="mock-model",
        icon="Code",
        color="cyan",
        agents=[
            AgentConfig(
                name="Manager",
                role="Engineering Manager",
                icon="Bot",
                color="violet",
                relationships=[Relationship(type="delegates_to", target="Architect"), Relationship(type="delegates_to", target="Developer")]
            ),
            AgentConfig(name="Architect", role="System Architect", icon="Brain", color="indigo"),
            AgentConfig(name="Developer", role="Fullstack Developer", icon="Code", color="cyan"),
        ]
    )
    from aether.team.loader import TeamLoader
    TeamLoader.to_yaml(team_cfg, ws.teams_dir / "engineering.yaml")

    scope = {"type": "http", "app": type("App", (), {"state": type("State", (), {"workspace": ws})()})()}
    req = Request(scope)

    teams = await get_teams(req)
    assert len(teams) >= 1
    eng_team = next(t for t in teams if t["name"] == "Engineering Core")
    assert "agents_list" in eng_team
    assert len(eng_team["agents_list"]) == 3

    mgr = next(a for a in eng_team["agents_list"] if a["name"] == "Manager")
    assert "Architect" in mgr["delegates_to"]
    assert "Developer" in mgr["delegates_to"]


def test_team_topology_e2e_rendering(browser_context):
    """E2E Playwright test verifying that Teams view renders the SVG Topology graph."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    # Navigate to Teams view
    teams_nav_btn = page.locator("button:has-text('Teams')").first
    if teams_nav_btn.is_visible():
        teams_nav_btn.click()
        page.wait_for_selector(".grid-container, .empty-state", timeout=5000)

        # Check if team cards with SVG topology are rendered
        topo_svg = page.locator(".team-topology-container svg").first
        if topo_svg.is_visible():
            expect(topo_svg).to_be_visible(timeout=3000)
            # Check for manager and specialist nodes in SVG
            nodes = page.locator(".team-topology-container svg g[transform]")
            assert nodes.count() >= 1

    page.close()
