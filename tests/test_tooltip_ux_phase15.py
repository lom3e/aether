"""
Test suite for P2-06: Universal Tooltip Component and Accessibility.
Verifies Tooltip component implementation, CSS classes, aria-label propagation,
and Playwright UI hover rendering.
"""
import os
import re
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


def test_tooltip_source_files_exist():
    """Verify that Tooltip component and CSS rules exist in the UI source."""
    repo_root = Path(__file__).parent.parent
    tooltip_tsx = repo_root / "ui" / "src" / "Tooltip.tsx"
    index_css = repo_root / "ui" / "src" / "index.css"

    assert tooltip_tsx.exists(), "ui/src/Tooltip.tsx must exist"
    assert index_css.exists(), "ui/src/index.css must exist"

    content = tooltip_tsx.read_text(encoding="utf-8")
    assert "export function Tooltip" in content
    assert "role=\"tooltip\"" in content
    assert "createPortal" in content
    assert "aria-label" in content

    css = index_css.read_text(encoding="utf-8")
    assert ".aether-tooltip" in css
    assert "tooltipFadeIn" in css


def test_tooltip_usage_in_key_components():
    """Verify that key components import and wrap actions with Tooltip."""
    repo_root = Path(__file__).parent.parent
    sidebar_tsx = repo_root / "ui" / "src" / "Sidebar.tsx"
    msg_tsx = repo_root / "ui" / "src" / "MessageItem.tsx"
    knowledge_tsx = repo_root / "ui" / "src" / "Knowledge.tsx"

    for file_path in [sidebar_tsx, msg_tsx, knowledge_tsx]:
        text = file_path.read_text(encoding="utf-8")
        assert "from './Tooltip'" in text, f"{file_path.name} must import Tooltip"
        assert "<Tooltip" in text, f"{file_path.name} must use <Tooltip"


def test_tooltip_e2e_hover_rendering(browser_context):
    """E2E test verifying that hovering over icon buttons triggers the Tooltip portal."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    # Hover over Command Palette ⌘K button
    cmd_k_btn = page.locator("button:has-text('⌘K')").first
    if cmd_k_btn.is_visible():
        cmd_k_btn.hover()
        page.wait_for_timeout(400)
        # Check tooltip portal element
        tooltip = page.locator(".aether-tooltip").first
        expect(tooltip).to_be_visible(timeout=3000)
        assert "Command Palette" in tooltip.text_content()

    page.close()
