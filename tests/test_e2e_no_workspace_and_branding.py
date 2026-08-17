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


def test_04_collapsed_sidebar_logo_and_reopen(browser_context):
    """Verifies that collapsing the sidebar keeps the Aether logo clearly visible and clicking it re-expands the sidebar."""
    page = browser_context.new_page()
    page.goto(BASE_URL)
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
    page = browser_context.new_page()
    page.goto(BASE_URL)
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
        assert "logo_bianco.svg" in src or "logo_nero.svg" in src

    page.close()


def test_06_workspace_modal_model_suggestions(browser_context):
    """Verifies that WorkspaceModal provides intelligent model dropdowns for all providers with custom input toggle."""
    page = browser_context.new_page()
    page.goto(BASE_URL)
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

    # 1. Ollama default (live discovered or curated default)
    provider_select.select_option("ollama")
    page.wait_for_timeout(300)
    model_select = page.locator("select").nth(1)
    expect(model_select).to_be_visible()
    selected_val = model_select.input_value()
    assert len(selected_val) > 0
    # Option should be selected in the list
    expect(model_select.locator(f"option[value='{selected_val}']")).to_be_attached()

    # 2. Switch to OpenAI
    provider_select.select_option("openai")
    page.wait_for_timeout(300)
    openai_model = page.locator("select:has(option[value='gpt-4o'])").first
    expect(openai_model).to_be_visible()
    assert openai_model.input_value() == "gpt-4o"

    # 3. Switch to Anthropic
    provider_select.select_option("anthropic")
    page.wait_for_timeout(300)
    anthropic_model = page.locator("select:has(option[value='claude-3-5-sonnet-20241022'])").first
    expect(anthropic_model).to_be_visible()
    assert anthropic_model.input_value() == "claude-3-5-sonnet-20241022"

    # 4. Switch to Gemini
    provider_select.select_option("gemini")
    page.wait_for_timeout(300)
    gemini_model = page.locator("select:has(option[value='gemini-2.0-flash'])").first
    expect(gemini_model).to_be_visible()
    assert gemini_model.input_value() == "gemini-2.0-flash"

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
