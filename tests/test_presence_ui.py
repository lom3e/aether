"""Presence: Aether opens on the orb (the transcript is one click away and remembered), the day sits around it, and
Rewind shows every change with Undo and "back to before this" (timeline routes mocked; the rest is the real server)."""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect, sync_playwright

_state: dict = {}


@pytest.fixture(scope="module")
def browser_context(aether_server):
    _state["base_url"] = aether_server["base_url"]
    _state["token"] = aether_server.get("token")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        context.add_init_script("localStorage.setItem('aether_language', 'en');")
        if _state["token"]:
            context.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{_state['token']}';")
        yield context
        browser.close()


TODAY = {"date": "2026-10-24", "brief": "", "empty": False, "calendar_error": "", "pending_approvals": 1,
         "counts": {"events": 1, "overdue": 1, "today": 0, "upcoming": 0},
         "events": [{"title": "Lezione di Analisi", "start": 4102444800, "location": "", "all_day": False}],
         "jobs": {"overdue": [{"id": "j1", "contact_id": None, "title": "Preventivo Rossi", "status": "open", "due_at": 1700000000, "notes": ""}], "today": [], "upcoming": [], "undated": []},
         "reminders": {"overdue": [], "today": [], "undated": []}}
TIMELINE = {"items": [
    {"execution_id": "ex-2", "action_id": "gmail.trash", "title": "Saldi -50%", "created_at": "2026-10-24T12:00:00+00:00", "reversible": True, "reason": "", "undone": False, "service": "gmail"},
    {"execution_id": "ex-1", "action_id": "gmail.send", "title": "Preventivo", "created_at": "2026-10-24T11:00:00+00:00", "reversible": False, "reason": "already_sent", "undone": False, "service": "gmail"},
]}


def test_presence_is_home_with_the_day_and_the_transcript_one_click_away(browser_context):
    page = browser_context.new_page()
    page.route("**/api/life/today*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(TODAY)))
    page.goto(_state["base_url"])
    expect(page.get_by_test_id("presence")).to_be_visible(timeout=20000)
    expect(page.get_by_role("heading", level=1)).to_contain_text("Good")
    day = page.get_by_test_id("presence-day")
    expect(day).to_contain_text("Lezione di Analisi")
    expect(day).to_contain_text("1 overdue")
    expect(day).to_contain_text("1 to confirm")
    page.get_by_test_id("presence-open-transcript").click()
    expect(page.get_by_test_id("open-presence")).to_be_visible()
    page.reload()
    expect(page.get_by_test_id("open-presence")).to_be_visible(timeout=15000)  # the choice is remembered
    page.get_by_test_id("open-presence").click()
    expect(page.get_by_test_id("presence")).to_be_visible()
    page.close()


def test_rewind_lists_changes_explains_what_cannot_be_undone_and_rewinds_on_confirmation(browser_context):
    page = browser_context.new_page()
    calls: list = []
    page.route("**/api/undo/timeline*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(TIMELINE)))
    page.route("**/api/undo/rewind/ex-2", lambda r: (calls.append(r.request.method), r.fulfill(status=200, content_type="application/json",
                                                                                             body=json.dumps({"undone": [{"execution_id": "ex-2", "title": "Saldi -50%"}], "kept": []})))[1])
    page.goto(_state["base_url"])
    page.evaluate("localStorage.setItem('aether_home_view', 'presence')")
    page.reload()
    page.get_by_test_id("presence-open-rewind").click()
    panel = page.get_by_test_id("rewind")
    expect(panel).to_be_visible()
    expect(page.get_by_test_id("rw-item-ex-2")).to_contain_text("Moved to Trash")
    expect(page.get_by_test_id("rw-item-ex-1")).to_contain_text("Already sent: an email cannot be recalled")
    expect(page.get_by_test_id("rw-undo-ex-1")).to_have_count(0)
    page.get_by_test_id("rw-rewind-ex-2").click()
    assert calls == [], "the first click only asks for confirmation"
    page.get_by_test_id("rw-rewind-confirm-ex-2").click()
    page.wait_for_timeout(500)
    assert calls == ["POST"]
    page.keyboard.press("Escape")
    expect(panel).to_have_count(0)
    page.close()


def test_promise_keeper_lists_what_was_promised_and_tracks_only_what_you_pick(browser_context):
    page = browser_context.new_page()
    scan = {"status": "ok", "scanned": 5, "items": [
        {"kind": "i_promised", "title": "Send the quote", "who": "Mario Rossi", "due_at": 4102444800, "message_id": "s1", "subject": "Re: website", "contact": None},
        {"kind": "they_asked", "title": "Send the October invoice", "who": "Laura Bianchi", "due_at": None, "message_id": "r1", "subject": "Invoice", "contact": None}]}
    page.route("**/api/life/promises/scan", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(scan)))
    page.goto(_state["base_url"])
    page.evaluate("localStorage.setItem('aether_home_view', 'presence')")
    page.reload()
    page.get_by_test_id("presence-open-promises").click()
    items = page.get_by_test_id("promise-item")
    expect(items).to_have_count(2)
    expect(items.first).to_contain_text("You promised Mario Rossi")
    expect(items.nth(1)).to_contain_text("Laura Bianchi asked you")
    jobs_before = page.evaluate("async () => (await (await fetch('/api/life/jobs')).json()).items.length")
    items.first.get_by_test_id("promise-save").click()
    expect(items.first).to_contain_text("Tracked")
    jobs = page.evaluate("async () => (await (await fetch('/api/life/jobs')).json()).items")
    assert len(jobs) == jobs_before + 1 and any(j["title"] == "Send the quote" for j in jobs)
    page.close()
