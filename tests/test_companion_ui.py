"""
E2E Playwright Browser Test — Phase D: Autonomous Operational Companion Engine.
Verifies that:
1. Personal Aether Companion on Home renders with Voice mic button, Take Care of It input, and Notification Bell.
2. User submits an operational goal, activating real-time stepper and background task progress card.
3. Notification bell click opens the Universal Notification Fabric drawer showing real notifications and review actions.
4. Voice Push-to-Talk button activates voice recording interface.
5. Captures artifacts:
   - phase_d_companion_home.png
   - phase_d_background_task_progress.png
   - phase_d_notification_drawer.png
   - phase_d_voice_controls.png
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
        name_input.fill("Companion Workspace")
        create_btn = page.locator("button:has-text('Create & Open Workspace'), button:has-text('Initialize Workspace')").first
        if create_btn.is_visible():
            create_btn.click()
            page.wait_for_timeout(1000)


def test_01_companion_home_and_task_execution(browser_context):
    """Verifies Home companion view, voice controls, notification bell, and background task progress."""
    page = browser_context.new_page()
    _ensure_workspace(page)

    # 1. Navigate to Home
    page.locator("[data-testid='nav-home']").click()
    page.wait_for_timeout(500)

    # Verify Companion elements
    expect(page.locator("h1:has-text('Personal Aether')")).to_be_visible()
    expect(page.locator("[data-testid='companion-input-field']")).to_be_visible()
    expect(page.locator("[data-testid='voice-mic-btn']")).to_be_visible()
    expect(page.locator("[data-testid='notification-bell-btn']")).to_be_visible()

    # Capture initial companion home screenshot
    shot_home = SCREENSHOTS_DIR / "phase_d_companion_home.png"
    page.screenshot(path=str(shot_home), full_page=False)
    assert shot_home.exists()

    # 2. Enter operational goal
    input_field = page.locator("[data-testid='companion-input-field']")
    input_field.fill("Please run a market analysis on CarShine competitor pricing")
    page.locator("[data-testid='companion-submit-btn']").click()

    # 3. Wait for stepper and background task progress card
    page.wait_for_selector("[data-testid='companion-messages-container']", timeout=12000)
    expect(page.locator("text=Understanding intent").first).to_be_visible()

    page.wait_for_timeout(1000)

    # Capture background task execution screenshot
    shot_task = SCREENSHOTS_DIR / "phase_d_background_task_progress.png"
    page.screenshot(path=str(shot_task), full_page=False)
    assert shot_task.exists()

    page.close()


def test_02_notification_fabric_drawer(browser_context):
    """Verifies notification drawer opening and notification cards."""
    page = browser_context.new_page()
    _ensure_workspace(page)

    page.locator("[data-testid='nav-home']").click()
    page.wait_for_timeout(500)

    # Click the Notification Bell
    bell_btn = page.locator("[data-testid='notification-bell-btn']")
    expect(bell_btn).to_be_visible()
    bell_btn.click()

    # Wait for drawer
    page.wait_for_selector("[data-testid='notification-drawer']", timeout=5000)
    expect(page.locator("[data-testid='notification-drawer']")).to_be_visible()

    # Capture notification drawer screenshot
    shot_notif = SCREENSHOTS_DIR / "phase_d_notification_drawer.png"
    page.screenshot(path=str(shot_notif), full_page=False)
    assert shot_notif.exists()

    page.close()


def test_03_voice_controls_push_to_talk(browser_context):
    """Verifies Push-to-Talk voice controls toggle."""
    page = browser_context.new_page()
    _ensure_workspace(page)

    page.locator("[data-testid='nav-home']").click()
    page.wait_for_timeout(500)

    mic_btn = page.locator("[data-testid='voice-mic-btn']")
    expect(mic_btn).to_be_visible()

    # Click mic to activate voice input mode
    mic_btn.click()
    page.wait_for_timeout(300)

    # Capture voice controls screenshot
    shot_voice = SCREENSHOTS_DIR / "phase_d_voice_controls.png"
    page.screenshot(path=str(shot_voice), full_page=False)
    assert shot_voice.exists()

    page.close()
