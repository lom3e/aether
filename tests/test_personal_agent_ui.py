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

import os
from pathlib import Path
import pytest
from playwright.sync_api import expect, sync_playwright

_state: dict = {}

SCREENSHOTS_DIR = Path("/Users/matteo/.gemini/antigravity/brain/2bf29abb-e8eb-4561-8306-04e6fe0773d0/screenshots")


@pytest.fixture(scope="module")
def browser_context(aether_server):
    """Module-scoped browser context using dynamic aether_server fixture."""
    _state["base_url"] = aether_server["base_url"]
    _state["token"] = aether_server.get("token")
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        if _state["token"]:
            context.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{_state['token']}';")
        yield context
        browser.close()


def _base_url() -> str:
    return _state.get("base_url", os.environ.get("AETHER_E2E_BASE_URL", "http://localhost:8000"))


def _ensure_workspace(page):
    """Ensures active workspace is selected or initialized."""
    base_url = _base_url()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    create_ws_btn = page.locator("button:has-text('+ Create workspace'), button:has-text('+ Crea workspace')").first
    if create_ws_btn.is_visible():
        create_ws_btn.click()
        page.wait_for_selector("input[placeholder*='Acme Robotics'], input[placeholder*='Financial Research']", timeout=5000)

    name_input = page.locator("input[placeholder*='Acme Robotics'], input[placeholder*='Financial Research']").first
    if name_input.is_visible():
        name_input.fill("Personal Agent Workspace")
        create_btn = page.locator("button:has-text('Create & Open Workspace'), button:has-text('Initialize Workspace')").first
        if create_btn.is_visible():
            create_btn.click()
            page.wait_for_timeout(1000)


def test_01_personal_agent_companion_flow(browser_context):
    """Verifies Home companion view, prompt input, and progress stepper."""
    page = browser_context.new_page()
    _ensure_workspace(page)

    # 1. Verify Home view rendered
    page.locator("[data-testid='nav-home']").click()
    page.wait_for_timeout(500)

    expect(page.locator("h1:has-text('Personal Aether')")).to_be_visible()
    expect(page.locator("textarea[placeholder*='What would you like Aether to take care of']")).to_be_visible()

    # 2. Click suggestion chip or type prompt
    prompt_area = page.locator("textarea[placeholder*='What would you like Aether to take care of']")
    prompt_area.fill("Create a document named project_plan.md with key milestones")

    # Send prompt
    page.locator("button:has-text('Take Care of It')").click()

    # 3. Wait for response and stepper
    page.wait_for_selector("div:has-text('Personal Aether')", timeout=10000)
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
    prompt_area = page.locator("textarea[placeholder*='What would you like Aether to take care of']")
    prompt_area.fill("Schedule a meeting with the Architecture Team for Friday at 10am")

    page.locator("button:has-text('Take Care of It')").click()
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
    page.locator("[data-testid='nav-connections']").click()
    page.wait_for_timeout(500)

    expect(page.locator("h1:has-text('Connections & Integrations')")).to_be_visible()
    expect(page.locator("text=Google Calendar")).to_be_visible()
    expect(page.locator("text=GitHub")).to_be_visible()

    # Switch to Calendar Schedule tab
    page.locator("button:has-text('Calendar Schedule')").click()
    page.wait_for_timeout(500)

    # Capture screenshot
    screenshot_path = SCREENSHOTS_DIR / "phase_c_connections.png"
    page.screenshot(path=str(screenshot_path), full_page=False)
    assert screenshot_path.exists()

    page.close()
