"""Privacy screen: what leaves the computer, what Aether knows (with a real forget), and the undo history.
Data routes are mocked where noted (they exercise the UI's mapping and calls); the settings toggle hits the real server."""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect, sync_playwright

from test_personal_agent_ui import _ensure_workspace

_state: dict = {}


@pytest.fixture(scope="module")
def browser_context(aether_server):
    _state["base_url"] = aether_server["base_url"]
    _state["token"] = aether_server.get("token")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800}, locale="en-US")
        context.add_init_script("localStorage.setItem('aether_home_view', 'transcript');")
        if _state["token"]:
            context.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{_state['token']}';")
        yield context
        browser.close()


def _page(context):
    import test_personal_agent_ui as base

    base._state.update(_state)
    page = context.new_page()
    _ensure_workspace(page)
    return page


def test_privacy_screen_tabs_forget_undo_and_the_real_toggle(browser_context):
    page = _page(browser_context)
    calls: list = []
    page.route("**/api/memories?*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(
        [{"id": "mem-1", "category": "preference", "summary": "Prefers short answers", "content": "Prefers short answers"}])))
    page.route("**/api/memories/mem-1*", lambda r: (calls.append((r.request.method, r.request.url)), r.fulfill(status=200, content_type="application/json", body='{"deleted":true}'))[1])
    page.route("**/api/undo/timeline*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"items": [
        {"execution_id": "ex-1", "title": "report.md", "created_at": 1760000000, "reversible": True, "reason": "", "undone": False, "kind": "restore"},
        {"execution_id": "ex-2", "title": "old.md", "created_at": 1760000100, "reversible": False, "reason": "changed_since", "undone": False}]})))
    undone: list = []
    page.route("**/api/undo/ex-1", lambda r: (undone.append(r.request.method), r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))[1])

    page.locator("[data-testid='nav-privacy']").click()
    expect(page.get_by_test_id("privacy-view")).to_be_visible()
    expect(page.get_by_test_id("privacy-out")).to_contain_text("nothing was sent to cloud models")
    toggle = page.get_by_test_id("privacy-redact-toggle")
    page.wait_for_timeout(600)
    before = toggle.is_checked()
    toggle.click()
    page.wait_for_timeout(400)
    page.reload()
    page.locator("[data-testid='nav-privacy']").click()
    if before:  # the control starts "on" until the stored value arrives, so wait for the real value
        expect(page.get_by_test_id("privacy-redact-toggle")).not_to_be_checked()
    else:
        expect(page.get_by_test_id("privacy-redact-toggle")).to_be_checked()

    page.get_by_test_id("privacy-tab-knows").click()
    expect(page.get_by_test_id("privacy-knows")).to_contain_text("Prefers short answers")
    edits: list = []
    page.route("**/api/memories/mem-1", lambda r: (edits.append((r.request.method, json.loads(r.request.post_data or "{}"))), r.fulfill(status=200, content_type="application/json", body='{"id":"mem-1"}'))[1] if r.request.method == "PATCH" else r.fallback())
    page.get_by_test_id("privacy-edit-mem-1").click()
    page.get_by_test_id("privacy-edit-input").fill("Prefers detailed answers")
    page.get_by_test_id("privacy-edit-save").click()
    expect(page.get_by_test_id("privacy-knows")).to_contain_text("Prefers detailed answers")
    assert edits == [("PATCH", {"summary": "Prefers detailed answers", "content": "Prefers detailed answers"})]
    page.get_by_role("button", name="Forget").first.click()
    expect(page.get_by_test_id("privacy-knows")).not_to_contain_text("Prefers short answers")
    assert calls and calls[0][0] == "DELETE" and "hard=true" in calls[0][1]

    page.get_by_test_id("privacy-tab-undo").click()
    expect(page.get_by_test_id("privacy-undo")).to_contain_text("cannot undo safely")
    page.get_by_test_id("undo-ex-1").click()
    page.wait_for_timeout(300)
    assert undone == ["POST"]
    assert page.get_by_test_id("undo-ex-2").count() == 0, "an unsafe undo is never offered"
    page.close()
