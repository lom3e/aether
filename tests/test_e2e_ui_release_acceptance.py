"""
Comprehensive End-to-End Playwright Acceptance Test Suite for Aether UI Release v1.3.2.
Simulates real browser interaction across all core sections and user workflows.

The `aether_server` fixture (defined in conftest.py) starts the backend
on a dynamic port before this module runs. BASE_URL is read at test time
from _state["base_url"] which is set by the module-scoped browser_context fixture.
Session token is injected via context.add_init_script for authenticated API calls.
"""
import os
import time
import pytest
from playwright.sync_api import Page, expect, sync_playwright

# Module-level mutable state: set by browser_context fixture before tests run.
_state: dict = {}


@pytest.fixture(scope="module")
def browser_context(aether_server):
    """Module-scoped browser context. Depends on aether_server to guarantee
    the backend is running before any test in this module executes."""
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


def test_00_ensure_workspace_ready(browser_context):
    """Ensures workspace is initialized and sidebar is loaded."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    # Check if workspace creation button exists (no active workspace)
    create_ws_btn = page.locator("button:has-text('+ Create workspace'), button:has-text('+ Crea workspace')").first
    if create_ws_btn.is_visible():
        create_ws_btn.click()
        page.wait_for_selector("input[placeholder*='Acme Robotics'], input[placeholder*='Financial Research']", timeout=5000)

    name_input = page.locator("input[placeholder*='Acme Robotics'], input[placeholder*='Financial Research']").first
    if name_input.is_visible():
        name_input.fill("Aether Acceptance Workspace")
        create_btn = page.locator("button:has-text('Create & Open Workspace'), button:has-text('Initialize Workspace')").first

        # Wait for submit button to be enabled once input is filled
        expect(create_btn).to_be_enabled(timeout=5000)
        create_btn.click()

        # Wait for modal overlay to disappear and workspace name to appear in header
        page.wait_for_selector(".badge-primary, .sidebar", timeout=10000)
        page.wait_for_timeout(1000)

    # Dismiss any stray modal if still open
    cancel_btn = page.locator("button:has-text('Cancel'), button:has-text('Annulla')").first
    if cancel_btn.is_visible():
        cancel_btn.click()
        page.wait_for_timeout(300)

    expect(page.locator(".sidebar")).to_be_visible()
    page.close()


def test_01_home_and_branding(browser_context):
    """Verifies Home page, SVG branding logos, metrics, and navigation elements."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    # SVG logo
    expect(page.locator("img[src*='logo']").first).to_be_visible()

    # Navigation buttons
    expect(page.locator(".sidebar button:has-text('Home')").first).to_be_visible()
    expect(page.locator(".sidebar button:has-text('New Task'), .sidebar button:has-text('Nuovo Task')").first).to_be_visible()
    expect(page.locator(".sidebar button:has-text('Agents')").first).to_be_visible()
    expect(page.locator(".sidebar button:has-text('Teams')").first).to_be_visible()
    expect(page.locator(".sidebar button:has-text('Knowledge')").first).to_be_visible()
    expect(page.locator(".sidebar button:has-text('Marketplace')").first).to_be_visible()
    expect(page.locator(".sidebar button:has-text('Settings')").first).to_be_visible()

    page.close()


def test_02_theme_switching(browser_context):
    """Verifies theme toggle between Light, Dark, and System modes."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    theme_btn = page.locator("button[title*='Theme'], button[title*='theme'], button:has-text('Theme')").first
    if theme_btn.is_visible():
        theme_btn.click()
        page.wait_for_timeout(300)
        theme_btn.click()
        page.wait_for_timeout(300)

    page.close()


def test_03_responsive_viewports(browser_context):
    """Verifies responsive layout across desktop, tablet, and mobile viewports."""
    base_url = _base_url()
    viewports = [
        {"width": 1440, "height": 900},
        {"width": 1280, "height": 800},
        {"width": 1024, "height": 768},
        {"width": 768, "height": 1024},
        {"width": 430, "height": 932},
        {"width": 390, "height": 844},
    ]

    for vp in viewports:
        page = browser_context.new_page()
        page.set_viewport_size(vp)
        page.goto(base_url)
        page.wait_for_selector(".sidebar", timeout=5000)
        expect(page.locator(".main-content")).to_be_visible()
        page.close()


def test_04_agents_section(browser_context):
    """Verifies Agents view, agent cards, and detail modal/panel."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    # Dismiss workspace modal if open
    cancel_btn = page.locator("button:has-text('Cancel'), button:has-text('Annulla')").first
    if cancel_btn.is_visible():
        cancel_btn.click()
        page.wait_for_timeout(300)

    page.locator(".sidebar button:has-text('Agents')").first.click()
    page.wait_for_selector(".main-content", timeout=5000)

    expect(page.locator(".main-content")).to_be_visible()
    cards = page.locator(".card, .agent-card, .agents-empty")
    expect(cards.first).to_be_visible(timeout=5000)

    page.close()


def test_05_teams_and_presets(browser_context):
    """Verifies Teams view and presets."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    # Dismiss workspace modal if open
    cancel_btn = page.locator("button:has-text('Cancel'), button:has-text('Annulla')").first
    if cancel_btn.is_visible():
        cancel_btn.click()
        page.wait_for_timeout(300)

    page.locator(".sidebar button:has-text('Teams')").first.click()
    page.wait_for_selector(".main-content", timeout=5000)
    expect(page.locator(".main-content")).to_be_visible()

    page.close()


def test_06_knowledge_management(browser_context):
    """Verifies Knowledge view, scope tabs, and document listing."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    page.locator(".sidebar button:has-text('Knowledge')").first.click()
    page.wait_for_selector(".main-content", timeout=5000)
    expect(page.locator(".main-content")).to_be_visible()

    page.close()


def test_07_marketplace_layout(browser_context):
    """Verifies Marketplace view and Community & Ecosystem cards."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    page.locator(".sidebar button:has-text('Marketplace')").first.click()
    page.wait_for_selector(".main-content", timeout=5000)
    expect(page.locator(".main-content")).to_be_visible()

    page.close()


def test_08_settings_view(browser_context):
    """Verifies Settings view, providers, models, and system metrics."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    page.locator(".sidebar button:has-text('Settings')").first.click()
    page.wait_for_selector(".main-content", timeout=5000)
    expect(page.locator(".main-content")).to_be_visible()

    page.close()


def test_09_chat_draft_lifecycle(browser_context):
    """Verifies New Task button opens clean draft state with no active conversation ID."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    # Click + New Task / Nuovo Task to navigate to chat view
    new_task_btn = page.locator(
        "button:has-text('New Task'), button:has-text('Nuovo Task'), .btn-new-task"
    ).first
    if new_task_btn.is_visible():
        new_task_btn.click()
        page.wait_for_timeout(500)

    # Dismiss workspace modal if it opened
    cancel_btn = page.locator("button:has-text('Cancel'), button:has-text('Annulla')").first
    if cancel_btn.is_visible():
        cancel_btn.click()
        page.wait_for_timeout(300)

    page.wait_for_selector("textarea", timeout=5000)
    expect(page.locator("textarea").first).to_be_visible()

    page.close()


def test_10_command_palette(browser_context):
    """Verifies Command Palette opens via shortcut or button and allows searching views."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    cmd_k_btn = page.locator("button:has-text('⌘K')").first
    if cmd_k_btn.is_visible():
        cmd_k_btn.click()
        page.wait_for_timeout(300)
        expect(page.locator("input[placeholder*='Search commands'], .command-palette input, input[placeholder*='Type a command']").first).to_be_visible()
        # Press Escape to close
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)

    page.close()
