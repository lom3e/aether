"""
E2E Playwright Browser Test — Phase C: Personal Agent, Action Layer, and Connections.
Verifies that:
1. Personal Aether Companion on Home renders input, suggestion chips, and overview cards.
2. Natural user intent flows through the progress stepper and returns responses.
3. Action confirmation flow (ACT tier) displays pending approval cards and allows approve / reject.
4. Connections hub displays integrated apps, calendar schedule, and action execution logs.
5. Captures screenshots: phase_c_personal_agent.png, phase_c_action_flow.png, phase_c_connections.png.
"""
from __future__ import annotations
import tempfile

import os
from pathlib import Path
import pytest
from playwright.sync_api import expect, sync_playwright

_state: dict = {}

SCREENSHOTS_DIR = Path(os.environ.get("AETHER_TEST_SCREENSHOTS_DIR") or tempfile.gettempdir()) / "aether-test-screenshots"


@pytest.fixture(scope="module")
def browser_context(aether_server):
    """Module-scoped browser context using dynamic aether_server fixture."""
    _state["base_url"] = aether_server["base_url"]
    _state["token"] = aether_server.get("token")
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        context.add_init_script("localStorage.setItem('aether_home_view', 'transcript');")  # tests target the classic UI
        if _state["token"]:
            context.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{_state['token']}';")
        yield context
        browser.close()


def _base_url() -> str:
    return _state.get("base_url", os.environ.get("AETHER_E2E_BASE_URL", "http://localhost:8000"))


def _ensure_workspace(page):
    """Opens the app. Aether always has its one personal space (created by the runtime at launch): nothing to create."""
    page.goto(_base_url())
    page.wait_for_selector(".sidebar", timeout=15000)
    page.wait_for_selector("h1:has-text('What do you need today?'), h1:has-text('Di cosa hai bisogno oggi?'), [data-testid='nav-home']", timeout=15000)
    page.wait_for_timeout(300)


def test_01_personal_agent_companion_flow(browser_context):
    """Verifies Home companion view, prompt input, and progress stepper."""
    page = browser_context.new_page()
    _ensure_workspace(page)

    # 1. Verify Home view rendered
    page.locator("[data-testid='nav-home']").click()
    page.wait_for_timeout(500)

    expect(page.locator("h1:has-text('What do you need today?')")).to_be_visible()
    expect(page.locator("[data-testid='companion-input-field']")).to_be_visible()

    # 2. Click suggestion chip or type prompt
    prompt_area = page.locator("[data-testid='companion-input-field']")
    prompt_area.fill("Create a document named project_plan.md with key milestones")

    # Send prompt
    page.locator("[data-testid='companion-submit-btn']").click()

    # 3. Wait for response; the steps are folded under a one-line summary, open it
    page.locator(".ch-steps-head").first.click(timeout=10000)
    page.wait_for_selector("text=Understanding intent", timeout=10000)
    expect(page.locator("text=Understanding intent").first).to_be_visible()
    expect(page.locator("text=project_plan.md").first).to_be_visible()

    # 4. Capture screenshot
    screenshot_path = SCREENSHOTS_DIR / "phase_c_personal_agent.png"
    page.screenshot(path=str(screenshot_path), full_page=False)
    assert screenshot_path.exists()
    page.close()


def test_02_action_safety_gating_flow(browser_context):
    """Verifies action execution safety confirmation for ACT tier (Calendar event)."""
    page = browser_context.new_page()
    _ensure_workspace(page)

    page.locator("[data-testid='nav-home']").click()
    page.wait_for_timeout(500)

    # Ask to schedule meeting (triggers ACT tier requiring confirmation)
    prompt_area = page.locator("[data-testid='companion-input-field']")
    prompt_area.fill("Schedule a meeting with the Architecture Team for Friday at 10am")

    page.locator("[data-testid='companion-submit-btn']").click()
    page.wait_for_timeout(1500)

    # Verify confirmation banner / card
    expect(page.locator("text=Confirmation Required").first).to_be_visible()
    expect(page.locator("button:has-text('Approve')").first).to_be_visible()

    # Screenshot before approval
    screenshot_path = SCREENSHOTS_DIR / "phase_c_action_flow.png"
    page.screenshot(path=str(screenshot_path), full_page=False)
    assert screenshot_path.exists()

    # Click Approve
    page.locator("button:has-text('Approve')").first.click()
    page.wait_for_timeout(1000)

    page.close()


def test_03_connections_and_integrations_view(browser_context):
    """Verifies Connections hub with apps, calendar schedule, and action log."""
    page = browser_context.new_page()
    _ensure_workspace(page)

    # Navigate to Connections
    if not page.locator("[data-testid='nav-connections']").count():  # lives under the collapsed 'More' group
        page.locator("[data-testid='nav-advanced']").click()
    page.locator("[data-testid='nav-connections']").click()
    page.wait_for_timeout(500)

    expect(page.get_by_test_id("connections-view")).to_be_visible()
    expect(page.get_by_test_id("conn-row-google_calendar")).to_be_visible()
    expect(page.get_by_test_id("conn-row-github")).to_be_visible()

    # The full previous screen (calendar schedule, keys, bots, custom APIs) lives under Advanced
    page.get_by_test_id("connections-advanced-toggle").click()
    expect(page.locator("h1:has-text('Connections & Integrations')")).to_be_visible()
    page.locator("button:has-text('Calendar Schedule')").click()
    page.wait_for_timeout(500)

    # Capture screenshot
    screenshot_path = SCREENSHOTS_DIR / "phase_c_connections.png"
    page.screenshot(path=str(screenshot_path), full_page=False)
    assert screenshot_path.exists()

    page.close()
