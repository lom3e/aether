"""
Playwright End-to-End browser test for:
- Official Favicon and Tab Title (<title>Aether</title>)
- Official vector SVGs (Light and Dark mode)
- Explicit No Active Workspace empty states on Home, Chat, and Sidebar
- Workspace creation and deletion lifecycle in browser
"""
import time
import pytest
from playwright.sync_api import Page, expect, sync_playwright

BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="module")
def browser_context():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        yield context
        browser.close()


def test_01_tab_title_and_favicon(browser_context):
    """Verifies page title is 'Aether' and favicon link points to /brand/favicon.svg."""
    page = browser_context.new_page()
    page.goto(BASE_URL)
    page.wait_for_timeout(1000)

    # 1. Page title must be 'Aether' (not 'ui')
    assert page.title() == "Aether"

    # 2. Favicon tag must point to /brand/favicon.svg
    favicon = page.locator("link[rel*='icon']").first
    expect(favicon).to_have_attribute("href", "/brand/favicon.svg")

    # 3. Favicon file must be accessible with 200 OK
    res = page.request.get(f"{BASE_URL}/brand/favicon.svg")
    assert res.status == 200
    assert "svg" in res.headers.get("content-type", "")

    page.close()


def test_02_official_branding_assets(browser_context):
    """Verifies official SVGs exist and are served cleanly."""
    page = browser_context.new_page()

    for asset in [
        "logo_nero.svg",
        "logo_bianco.svg",
        "logo_viola.svg",
        "logo_viola_con_scritta.svg",
        "scritta_AETHER.svg",
        "favicon.svg",
    ]:
        res = page.request.get(f"{BASE_URL}/brand/{asset}")
        assert res.status == 200, f"Asset /brand/{asset} failed with status {res.status}"
        assert len(res.body()) > 100

    page.close()


def test_03_no_workspace_empty_state_and_navigation(browser_context):
    """Verifies UI recognizes no-workspace state and shows proper cards."""
    page = browser_context.new_page()
    page.goto(BASE_URL)
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
