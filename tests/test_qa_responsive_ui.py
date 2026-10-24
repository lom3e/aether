"""
Layout and theme checks of the primary screens in a real browser: no horizontal overflow at phone and tablet widths, the
chosen theme is applied and survives a reload, and no page raises JavaScript errors. Screenshots are written to
AETHER_TEST_SCREENSHOTS_DIR (or the temp dir) for inspection.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from test_personal_agent_ui import _ensure_workspace
from ui_isolation import clear_pending_work
from test_qa_localization_ui import _open_view

_state: dict = {}
SHOTS = Path(os.environ.get("AETHER_TEST_SCREENSHOTS_DIR") or tempfile.gettempdir()) / "aether-test-screenshots"
VIEWS = ["home", "missions", "connections", "results", "workforce", "automations", "settings", "marketplace"]
VIEWPORTS = {"phone": (375, 812), "tablet": (768, 1024), "desktop": (1440, 900)}


@pytest.fixture(scope="module")
def browser_context(aether_server):
    _state["base_url"] = aether_server["base_url"]
    _state["token"] = aether_server.get("token")
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        context.add_init_script("localStorage.setItem('aether_home_view', 'transcript');")
        if _state["token"]:
            context.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{_state['token']}';")
        yield context
        browser.close()


def _overflow(page) -> dict:
    return page.evaluate(
        "({inner: window.innerWidth, doc: document.documentElement.scrollWidth, "
        "main: (document.querySelector('.main-content') || document.body).scrollWidth, "
        "mainClient: (document.querySelector('.main-content') || document.body).clientWidth})"
    )


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("size", ["phone", "tablet", "desktop"])
def test_primary_screens_fit_the_viewport(browser_context, theme, size):
    import test_personal_agent_ui as base
    base._state.update(_state)
    width, height = VIEWPORTS[size]
    page = browser_context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _ensure_workspace(page); clear_pending_work(_state['base_url'], _state['token'])
    page.evaluate(f"localStorage.setItem('aether_theme', '{theme}')")
    page.set_viewport_size({"width": width, "height": height})
    page.reload()
    page.wait_for_selector(".sidebar", timeout=15000)
    page.wait_for_timeout(600)
    assert page.evaluate("document.documentElement.classList.contains('dark')") == (theme == "dark")
    problems = {}
    for view in VIEWS:
        if not _open_view(page, view):
            continue
        o = _overflow(page)
        if o["doc"] > o["inner"] + 1 or o["main"] > o["mainClient"] + 1:
            problems[view] = o
        page.screenshot(path=str(SHOTS / f"qa_{view}_{size}_{theme}.png"))
    page.close()
    assert not errors, errors
    assert not problems, f"horizontal overflow at {size}/{theme}: {problems}"


def test_the_theme_and_language_choices_persist_across_reloads(browser_context):
    import test_personal_agent_ui as base
    base._state.update(_state)
    page = browser_context.new_page()
    _ensure_workspace(page); clear_pending_work(_state['base_url'], _state['token'])
    page.evaluate("localStorage.setItem('aether_theme', 'dark'); localStorage.setItem('aether_language', 'it')")
    page.reload()
    page.wait_for_selector(".sidebar", timeout=15000)
    page.wait_for_timeout(500)
    assert page.evaluate("document.documentElement.classList.contains('dark')")
    assert "Impostazioni" in page.evaluate("document.body.innerText")
    page.close()
