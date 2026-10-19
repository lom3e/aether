"""Answer receipts in the Companion: what was injected, what left the computer, forget a memory, correct an answer.
The chat reply and the memory/learning routes are mocked (labelled: they exercise the UI's mapping and calls)."""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from test_personal_agent_ui import _ensure_workspace

_state: dict = {}
SHOTS = Path(os.environ.get("AETHER_TEST_SCREENSHOTS_DIR") or tempfile.gettempdir()) / "aether-test-screenshots"


@pytest.fixture(scope="module")
def browser_context(aether_server):
    _state["base_url"] = aether_server["base_url"]
    _state["token"] = aether_server.get("token")
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        context.add_init_script("localStorage.setItem('aether_experience_mode', 'v1');")
        if _state["token"]:
            context.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{_state['token']}';")
        yield context
        browser.close()


@pytest.fixture(scope="module")
def workspace_ready(browser_context):
    import test_personal_agent_ui as base

    base._state.update(_state)
    page = browser_context.new_page()
    _ensure_workspace(page)
    page.close()


def _reply(egress, sources):
    return {"id": "msg-r1", "session_id": "sess-r1", "role": "assistant", "content": "Your invoices are due on the 5th.",
            "metadata": {"egress": egress, "sources": sources}, "created_at": "2026-01-01T00:00:00Z"}


CLOUD = {"ids": ["eg-1"], "requests": 1, "local_only": False, "providers": ["groq"], "models": ["m"], "images": 0, "chars": 120,
         "redactions": {"iban": 1, "email": 1}, "redactions_total": 2, "unmasked": False}
SOURCES = [{"tag": "M1", "kind": "memory", "ref": "mem-42", "title": "Invoices are due on the 5th", "source": "user", "trust": "user_stated", "forgettable": True},
           {"tag": "K1", "kind": "knowledge", "ref": "chunk-7", "title": "contract.pdf", "source": "contract.pdf · chunk 3", "trust": "retrieved"}]


def _open(context, reply, calls):
    page = context.new_page()
    page.set_viewport_size({"width": 408, "height": 604})
    page.add_init_script("localStorage.setItem('aether_language', 'en');")
    page.route("**/api/personal/chat", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(reply)))
    page.route("**/api/memories/*", lambda r: (calls.append((r.request.method, r.request.url)), r.fulfill(status=200, content_type="application/json", body='{"deleted":true}'))[1])
    page.route("**/api/learning/corrections", lambda r: (calls.append(("POST", r.request.url, json.loads(r.request.post_data or "{}"))), r.fulfill(status=201, content_type="application/json", body='{"id":"corr-1"}'))[1])
    page.route("**/api/learning/corrections/*/verify", lambda r: (calls.append(("VERIFY", r.request.url)), r.fulfill(status=200, content_type="application/json", body='{"id":"lesson-1"}'))[1])
    page.goto(f"{_state['base_url']}/?surface=companion")
    expect(page.get_by_test_id("companion-panel")).to_be_visible(timeout=15000)
    page.get_by_test_id("companion-input").fill("When are my invoices due?")
    page.get_by_test_id("companion-send").click()
    expect(page.get_by_test_id("companion-msg-assistant").last).to_contain_text(re.compile("due on the 5th", re.I), timeout=15000)
    return page


def test_receipts_show_sources_and_what_left_the_computer(browser_context, workspace_ready):
    calls: list = []
    page = _open(browser_context, _reply(CLOUD, SOURCES), calls)
    toggle = page.get_by_test_id("companion-receipts-toggle")
    expect(toggle).to_have_text("Sources 2 · Sent to groq · 2 masked")
    assert page.get_by_test_id("companion-source").count() == 0, "details stay closed until asked for"
    toggle.click()
    rows = page.get_by_test_id("companion-source")
    expect(rows).to_have_count(2)
    expect(rows.first).to_contain_text("Memory")
    expect(rows.first).to_contain_text("Invoices are due on the 5th")
    expect(rows.nth(1)).to_contain_text("Document")
    assert page.get_by_test_id("companion-forget").count() == 1, "only memories can be forgotten from here"
    page.screenshot(path=str(SHOTS / "companion_receipts.png"))
    page.close()


def test_forgetting_a_memory_calls_the_runtime_and_removes_the_source(browser_context, workspace_ready):
    calls: list = []
    page = _open(browser_context, _reply(CLOUD, SOURCES), calls)
    page.get_by_test_id("companion-receipts-toggle").click()
    page.get_by_test_id("companion-forget").click()
    expect(page.get_by_test_id("companion-source")).to_have_count(1)
    assert calls and calls[0][0] == "DELETE" and calls[0][1].endswith("/api/memories/mem-42")
    expect(page.get_by_test_id("companion-receipts-toggle")).to_have_text("Sources 1 · Sent to groq · 2 masked")
    page.close()


def test_correcting_an_answer_creates_and_verifies_a_correction(browser_context, workspace_ready):
    calls: list = []
    page = _open(browser_context, _reply(CLOUD, SOURCES), calls)
    page.get_by_test_id("companion-receipts-toggle").click()
    page.get_by_test_id("companion-not-correct").click()
    send = page.get_by_test_id("companion-correction-send")
    expect(send).to_be_disabled()
    page.get_by_test_id("companion-correction-input").fill("Invoices are due on the 10th.")
    send.click()
    expect(page.get_by_test_id("companion-correction-input")).to_have_count(0, timeout=10000)
    post = next(c for c in calls if c[0] == "POST")
    assert post[2]["correction"] == "Invoices are due on the 10th." and post[2]["problem"].startswith("Your invoices")
    assert post[2]["evidence"]["message_id"] == "msg-r1" and {s["ref"] for s in post[2]["evidence"]["sources"]} == {"mem-42", "chunk-7"}
    assert any(c[0] == "VERIFY" and "corr-1" in c[1] for c in calls)
    page.close()


def test_local_only_and_unmasked_are_stated_plainly(browser_context, workspace_ready):
    local = {"ids": ["eg-2"], "requests": 1, "local_only": True, "providers": ["ollama"], "images": 0, "redactions": {}, "redactions_total": 0}
    page = _open(browser_context, _reply(local, []), [])
    expect(page.get_by_test_id("companion-receipts-toggle")).to_have_text("Stayed on this computer")
    page.close()
    unmasked = dict(CLOUD, redactions={}, redactions_total=0, unmasked=True)
    page = _open(browser_context, _reply(unmasked, []), [])
    expect(page.get_by_test_id("companion-receipts-toggle")).to_have_text("Sent to groq · sent unmasked")
    page.close()


def test_replies_without_receipts_show_nothing(browser_context, workspace_ready):
    page = _open(browser_context, {"id": "m", "session_id": "s", "role": "assistant", "content": "Due on the 5th.", "metadata": {}}, [])
    assert page.get_by_test_id("companion-receipts").count() == 0
    page.close()


def test_second_opinion_is_offered_only_with_two_providers_and_shows_the_comparison(browser_context, workspace_ready):
    # Mocked routes: they exercise the UI's gating, the request it sends and how disagreement is shown.
    page = browser_context.new_page()
    page.set_viewport_size({"width": 408, "height": 604})
    page.add_init_script("localStorage.setItem('aether_language', 'en');")
    sent: list = []
    page.route("**/api/personal/chat", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(_reply(CLOUD, SOURCES))))
    page.route("**/api/personal/second-opinion/providers", lambda r: r.fulfill(status=200, content_type="application/json", body='{"providers":["openai","groq"],"available":true}'))
    page.route("**/api/personal/second-opinion", lambda r: (sent.append(json.loads(r.request.post_data or "{}")), r.fulfill(status=200, content_type="application/json", body=json.dumps({
        "status": "ok",
        "opinions": [{"provider": "openai", "model": "m1", "status": "ok", "content": "Due on the 5th."},
                     {"provider": "groq", "model": "m2", "status": "ok", "content": "Due on the 15th."},
                     {"provider": "gemini", "status": "failed", "reason": "RuntimeError"}],
        "agreement": {"level": "partial", "similarity": 0.3, "differing_numbers": ["5", "15"]}})))[1])
    page.goto(f"{_state['base_url']}/?surface=companion")
    expect(page.get_by_test_id("companion-panel")).to_be_visible(timeout=15000)
    page.get_by_test_id("companion-input").fill("When are my invoices due?")
    page.get_by_test_id("companion-send").click()
    btn = page.get_by_test_id("companion-second-opinion-btn")
    expect(btn).to_be_visible(timeout=15000)
    btn.click()
    expect(page.get_by_test_id("companion-second-level")).to_contain_text("Partly different")
    expect(page.get_by_test_id("companion-second-level")).to_contain_text("5, 15")
    expect(page.get_by_test_id("companion-second-opinion")).to_contain_text("Due on the 15th.")
    expect(page.get_by_test_id("companion-second-opinion")).to_contain_text("No answer from this model.")
    assert sent == [{"question": "When are my invoices due?", "language": "en"}]
    page.close()
