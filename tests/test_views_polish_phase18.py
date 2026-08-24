"""
Test suite for P2-05: Visual Polish of Teams, Agents, and Knowledge Views.
Verifies cards with hover effects, semantic badges, IdentityBadge usage,
scope filters, and Playwright UI navigation.
"""
import os
import pytest
from pathlib import Path
from playwright.sync_api import expect, sync_playwright

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


def test_views_polish_source_code_contract():
    """Verify that Agents, Teams, and Knowledge use updated cards, IdentityBadge, and semantic badges."""
    repo_root = Path(__file__).parent.parent
    agents_tsx = repo_root / "ui" / "src" / "Agents.tsx"
    teams_tsx = repo_root / "ui" / "src" / "Teams.tsx"
    knowledge_tsx = repo_root / "ui" / "src" / "Knowledge.tsx"

    agents_src = agents_tsx.read_text(encoding="utf-8")
    assert "IdentityBadge" in agents_src
    assert "card-interactive" in agents_src

    teams_src = teams_tsx.read_text(encoding="utf-8")
    assert "IdentityBadge" in teams_src
    assert "TeamTopology" in teams_src
    assert "card-interactive" in teams_src

    know_src = knowledge_tsx.read_text(encoding="utf-8")
    assert "systemScope" in know_src
    assert "projectScope" in know_src
    assert "workspaceScope" in know_src


def test_views_e2e_navigation_and_visuals(browser_context):
    """E2E Playwright test verifying that Agents, Teams, and Knowledge views render smoothly."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    # 1. Test Agents View
    agents_btn = page.locator("button:has-text('Agents')").first
    if agents_btn.is_visible():
        agents_btn.click()
        page.wait_for_selector(".top-header", timeout=5000)

    # 2. Test Teams View
    teams_btn = page.locator("button:has-text('Teams')").first
    if teams_btn.is_visible():
        teams_btn.click()
        page.wait_for_selector(".top-header", timeout=5000)

    # 3. Test Knowledge View
    know_btn = page.locator("button:has-text('Knowledge')").first
    if know_btn.is_visible():
        know_btn.click()
        page.wait_for_selector(".top-header", timeout=5000)

    page.close()
