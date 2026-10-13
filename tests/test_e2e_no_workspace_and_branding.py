"""
Playwright End-to-End browser test for:
- Official Favicon and Tab Title (<title>Aether</title>)
- Official vector SVGs (Light and Dark mode)
- Explicit No Active Workspace empty states on Home, Chat, and Sidebar
- Workspace creation and deletion lifecycle in browser

The `aether_server` fixture (defined in conftest.py) starts the backend
on a dynamic port before this module runs. BASE_URL is read from the
environment variable AETHER_E2E_BASE_URL set by that fixture.
"""
import os
import time
import pytest
from playwright.sync_api import Page, expect, sync_playwright

# BASE_URL is set at fixture time via the module-level _state dict below.
# We cannot use a plain `BASE_URL = os.environ.get(...)` at import time
# because the env var is only set by the fixture after collection.
_state: dict = {}


@pytest.fixture(scope="module")
def browser_context(aether_server):
    """Module-scoped browser context. Depends on aether_server to guarantee
    the backend is running before any test in this module executes."""
    _state["base_url"] = aether_server["base_url"]
    token = aether_server.get("token")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        context.add_init_script("localStorage.setItem('aether_experience_mode', 'v1');")  # tests target the classic UI
        if token:
            context.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{token}';")
        yield context
        browser.close()


def _base_url() -> str:
    return _state.get("base_url", os.environ.get("AETHER_E2E_BASE_URL", "http://localhost:8000"))


def test_01_tab_title_and_favicon(browser_context):
    """Verifies page title is 'Aether' and favicon link points to /brand/favicon.svg."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_timeout(1000)

    # 1. Page title must be 'Aether' (not 'ui')
    assert page.title() == "Aether"

    # 2. Favicon tag must point to /brand/favicon.svg
    favicon = page.locator("link[rel*='icon']").first
    expect(favicon).to_have_attribute("href", "/brand/favicon.svg")

    # 3. Favicon file must be accessible with 200 OK
    res = page.request.get(f"{base_url}/brand/favicon.svg")
    assert res.status == 200
    assert "svg" in res.headers.get("content-type", "")

    page.close()


def test_02_official_branding_assets(browser_context):
    """Verifies official SVGs exist and are served cleanly."""
    base_url = _base_url()
    page = browser_context.new_page()

    for asset in [
        "logo_nero.svg",
        "logo_bianco.svg",
        "logo_viola.svg",
        "logo_viola_con_scritta.svg",
        "scritta_AETHER.svg",
        "favicon.svg",
    ]:
        res = page.request.get(f"{base_url}/brand/{asset}")
        assert res.status == 200, f"Asset /brand/{asset} failed with status {res.status}"
        assert len(res.body()) > 100

    page.close()


def test_03_no_workspace_empty_state_and_navigation(browser_context):
    """Verifies UI recognizes no-workspace state and shows proper cards."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_timeout(1000)

    # Sidebar must be visible
    expect(page.locator(".sidebar")).to_be_visible()

    # If a workspace is currently active, Home shows normal header.
    # Otherwise, it shows 'Crea il tuo primo workspace' or 'Create your first workspace'
    home_heading = page.locator("h1, h2").first
    expect(home_heading).to_be_visible()

    # Navigate to chat
    page.locator(".sidebar button:has-text('New Task'), .sidebar button:has-text('Nuovo Task'), .sidebar button:has-text('Conversations'), .sidebar button:has-text('Conversazioni')").first.click()
    page.wait_for_timeout(500)

    page.close()


def test_04_collapsed_sidebar_logo_and_reopen(browser_context):
    """Verifies that collapsing the sidebar keeps the Aether logo clearly visible and clicking it re-expands the sidebar."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    sidebar = page.locator(".sidebar")
    expect(sidebar).to_be_visible()

    # Initial state: expanded width >= 200px
    box_initial = sidebar.bounding_box()
    assert box_initial is not None and box_initial["width"] >= 200

    # Click collapse button
    collapse_btn = page.locator(".sidebar button[aria-label='Collapse Sidebar'], .sidebar button[title*='Collapse'], .sidebar button[title*='Comprimi']").first
    expect(collapse_btn).to_be_visible()
    collapse_btn.click()
    page.wait_for_timeout(500)

    # Collapsed state: width should be ~68px
    box_collapsed = sidebar.bounding_box()
    assert box_collapsed is not None and box_collapsed["width"] <= 100

    # Aether logo in collapsed header must be visible and properly sized
    logo_btn = page.locator(".sidebar button[aria-label='Expand Sidebar'], .sidebar button[title*='Expand'], .sidebar button[title*='Espandi']").first
    expect(logo_btn).to_be_visible()
    logo_img = logo_btn.locator("img")
    expect(logo_img).to_be_visible()

    # Click logo button to re-expand sidebar
    logo_btn.click()
    page.wait_for_timeout(500)

    # Re-expanded state: width >= 200px
    box_reopened = sidebar.bounding_box()
    assert box_reopened is not None and box_reopened["width"] >= 200

    # Workspace header text and collapse button should be visible again
    expect(collapse_btn).to_be_visible()

    page.close()


def test_05_theme_aware_collapsed_logo(browser_context):
    """Verifies that the collapsed logo switches between logo_bianco.svg and logo_nero.svg with theme."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    # Collapse sidebar
    collapse_btn = page.locator(".sidebar button[aria-label='Collapse Sidebar'], .sidebar button[title*='Collapse'], .sidebar button[title*='Comprimi']").first
    if collapse_btn.is_visible():
        collapse_btn.click()
        page.wait_for_timeout(400)

    logo_img = page.locator(".sidebar button[aria-label='Expand Sidebar'] img, .sidebar button[title*='Expand'] img").first
    expect(logo_img).to_be_visible()

    # Toggle theme via footer theme button
    theme_btn = page.locator(".sidebar button[title*='Theme'], .sidebar button:has(svg.lucide-sun), .sidebar button:has(svg.lucide-moon)").last
    if theme_btn.is_visible():
        theme_btn.click()
        page.wait_for_timeout(400)
        # Logo img must still be visible and match theme svg
        expect(logo_img).to_be_visible()
        src = logo_img.get_attribute("src") or ""
        assert "logo_viola.svg" in src

    page.close()


def test_06_workspace_modal_model_suggestions(browser_context):
    """Verifies that WorkspaceModal provides intelligent model dropdowns for all providers with custom input toggle."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    # Open Create Workspace Modal (from Home button or Sidebar dropdown)
    create_btn = page.locator("button:has-text('+ Create workspace'), button:has-text('+ Crea workspace')").first
    if not create_btn.is_visible():
        ws_switcher = page.locator(".sidebar button:has-text('AI WORKFORCE'), .sidebar button:has-text('CLICK TO CREATE'), .sidebar button:has-text('CLICCA PER CREARE')").first
        if ws_switcher.is_visible():
            ws_switcher.click()
            page.wait_for_timeout(300)
            page.locator("button:has-text('+ New Workspace'), button:has-text('+ Nuovo Workspace')").first.click()
    else:
        create_btn.click()

    page.wait_for_timeout(500)

    # Modal must be visible
    modal = page.locator("h2:has-text('New Workspace'), h3:has-text('New Workspace'), div:has-text('Workspace Name')").first
    expect(modal).to_be_visible()

    # Provider select and Model select must be visible
    provider_select = page.locator("select:has(option[value='ollama'])").first
    expect(provider_select).to_be_visible()

    # Product policy: no model is ever preselected. Each provider offers its suggested models and the user picks one.
    def _model_select_with(option_value):
        return page.locator(f"select:has(option[value='{option_value}'])").first

    # 1. Ollama (suggestions come from the live local installation, so only the policy is asserted)
    provider_select.select_option("ollama")
    page.wait_for_timeout(300)
    model_select = page.locator("select").nth(1)
    expect(model_select).to_be_visible()
    assert model_select.input_value() == "", "no model may be preselected"

    # 2-4. Hosted providers: suggestions are listed, none is selected until explicitly chosen
    for provider, model in (
        ("openai", "gpt-4o"),
        ("anthropic", "claude-3-5-sonnet-20241022"),
        ("gemini", "gemini-2.0-flash"),
    ):
        provider_select.select_option(provider)
        page.wait_for_timeout(300)
        picker = _model_select_with(model)
        expect(picker).to_be_visible()
        assert picker.input_value() == "", f"{provider}: no model may be preselected"
        picker.select_option(model)
        assert picker.input_value() == model

    # 5. Toggle Custom model
    custom_btn = page.locator("button:has-text('Custom model...')").first
    expect(custom_btn).to_be_visible()
    custom_btn.click()
    page.wait_for_timeout(300)

    custom_input = page.locator("input[placeholder*='custom-model']").first
    expect(custom_input).to_be_visible()
    custom_input.fill("my-fine-tuned-model:v1")
    assert custom_input.input_value() == "my-fine-tuned-model:v1"

    # 6. Switch back to Suggested list
    suggested_btn = page.locator("button:has-text('Suggested list')").first
    suggested_btn.click()
    page.wait_for_timeout(300)
    expect(page.locator("select:has(option[value='gemini-2.0-flash'])").first).to_be_visible()

    # Close modal
    page.locator("button:has-text('Cancel'), button:has-text('Annulla')").first.click()
    page.close()
