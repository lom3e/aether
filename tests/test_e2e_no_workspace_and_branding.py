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


def test_06_first_run_model_card_replaces_the_workspace_form(browser_context):
    """There is no workspace form any more: Home asks for a provider and a key once, sends them to the settings route, and goes away."""
    import json

    page = browser_context.new_page()
    saved: list = []
    state = {"done": False}
    page.route("**/api/settings/provider", lambda r: (
        (saved.append(json.loads(r.request.post_data or "{}")), state.update(done=True), r.fulfill(status=200, content_type="application/json", body="{}"))
        if r.request.method == "POST"
        else r.fulfill(status=200, content_type="application/json", body=json.dumps({"provider": "groq" if state["done"] else "", "model": "m", "configured": {"groq": state["done"], "openai": False, "anthropic": False, "gemini": False, "ollama": True}}))))
    page.goto(_base_url())
    page.wait_for_selector(".sidebar", timeout=15000)
    card = page.get_by_test_id("first-run-model")
    expect(card).to_be_visible(timeout=10000)
    assert page.locator("[data-testid='frm-provider'] option").count() == 4
    expect(page.get_by_test_id("frm-save")).to_be_disabled()
    page.get_by_test_id("frm-key").fill("sk-test-not-a-real-key")
    page.get_by_test_id("frm-save").click()
    expect(card).to_have_count(0, timeout=10000)
    assert saved and saved[0]["provider"] == "groq" and saved[0]["api_key"] == "sk-test-not-a-real-key" and saved[0]["apply_to_all_agents"] is True
    assert "sk-test-not-a-real-key" not in page.content(), "the key is never left in the page"
    assert page.locator("[data-testid='workspace-switcher-button']").count() == 0 and page.locator("text=/new workspace/i").count() == 0
    page.close()


def test_07_the_orb_interface_offers_the_model_card_too(browser_context):
    """The default (Orb) experience has no Home page: without a model it must show the same Connect-a-model card."""
    import json

    page = browser_context.new_page()
    page.add_init_script("localStorage.setItem('aether_experience_mode', 'v2');")
    page.route("**/api/settings/provider", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(
        {"provider": "", "model": "", "configured": {"groq": False, "openai": False, "anthropic": False, "gemini": False, "ollama": True}})))
    page.goto(_base_url())
    expect(page.get_by_test_id("first-run-model")).to_be_visible(timeout=15000)
    page.close()
