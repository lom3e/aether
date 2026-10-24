"""Home "Today" and the People & jobs view against the real server. The model that reads a sentence is mocked (labelled), so
the proposal -> save -> Today -> People -> forget path is real end to end."""
from __future__ import annotations

import json
import time

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
        context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
        context.add_init_script("localStorage.setItem('aether_home_view', 'transcript'); localStorage.setItem('aether_language', 'en');")
        if _state["token"]:
            context.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{_state['token']}';")
        yield context
        browser.close()


def test_capture_today_people_and_forget(browser_context):
    import test_personal_agent_ui as base

    base._state.update(_state)
    page = browser_context.new_page()
    _ensure_workspace(page)
    page.locator("[data-testid='nav-home']").click()
    expect(page.get_by_test_id("today-card")).to_be_visible(timeout=10000)
    expect(page.get_by_test_id("today-empty")).to_be_visible()

    due = time.time() + 3600  # later today or tomorrow morning: either way it must show up in Today or Coming up
    page.route("**/api/life/capture", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(
        {"status": "ok", "kind": "job", "title": "Send the quote", "notes": "", "due_at": due, "contact": {"id": None, "name": "Mario Rossi", "new": True}, "email": "", "phone": ""})))
    page.get_by_test_id("today-capture-input").fill("Rossi wants the quote by Friday")
    page.get_by_test_id("today-capture-btn").click()
    proposal = page.get_by_test_id("today-proposal")
    expect(proposal).to_contain_text("Send the quote")
    expect(proposal).to_contain_text("Mario Rossi (new)")
    jobs_before = page.evaluate("async () => (await (await fetch('/api/life/jobs')).json()).items.length")
    assert jobs_before == 0, "a proposal is not saved until the user accepts"
    page.get_by_test_id("today-proposal-save").click()
    expect(page.get_by_test_id("today-proposal")).to_have_count(0)
    page.reload()
    expect(page.get_by_test_id("today-card")).to_contain_text("Send the quote", timeout=10000)

    page.get_by_test_id("today-open-people").click()
    expect(page.get_by_test_id("people-view")).to_be_visible()
    page.get_by_text("Mario Rossi").first.click()
    expect(page.get_by_test_id("person-jobs")).to_contain_text("Send the quote")
    page.get_by_test_id("person-job-title").fill("Call him back")
    page.get_by_test_id("person-job-add").click()
    expect(page.get_by_test_id("person-jobs")).to_contain_text("Call him back")
    mem_count = page.evaluate("async () => (await (await fetch('/api/memories?limit=200')).json()).filter(m => (m.summary||'').includes('Rossi')).length")
    assert mem_count >= 1, "the client and the job are part of what Aether remembers"
    page.get_by_test_id("person-forget").click()
    expect(page.get_by_test_id("people-empty")).to_be_visible(timeout=10000)
    page.close()


def test_morning_brief_setting_is_off_by_default_and_saved_by_the_real_server(browser_context):
    import test_personal_agent_ui as base

    base._state.update(_state)
    page = browser_context.new_page()
    _ensure_workspace(page)
    page.locator("[data-testid='nav-settings']").click()
    page.get_by_role("tab", name="General").click()
    toggle = page.get_by_test_id("brief-toggle")
    expect(toggle).not_to_be_checked(timeout=10000)
    toggle.check()
    page.get_by_test_id("brief-time").fill("07:15")
    page.get_by_test_id("brief-time").blur()
    page.wait_for_timeout(500)
    saved = page.evaluate("async () => (await fetch('/api/life/settings')).json()")
    assert saved["brief_enabled"] is True and saved["brief_time"] == "07:15"
    page.close()
