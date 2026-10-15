"""
Companion 2.0 in a real browser against a real Aether server (isolated data dir, no AI provider configured).

The native window behaviour (compact orb, drag, follow) lives in src-tauri/src/companion.rs and is covered by its Rust
unit tests and by the packaged-app smoke test. These tests cover what the webview shows and how it talks to the runtime:
statuses that follow real runtime facts, the real "no provider" conversation, session continuity with the main Assistant,
orb <-> panel transitions, approvals/tasks as reported by the overview endpoint, and layout at small sizes.
Routes mocked with page.route() are labelled as such: they exercise the UI's mapping of runtime state, not the runtime.
"""
from __future__ import annotations

import json
import os
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


def _open(context, mode: str | None = None, size=(408, 604), language: str = "en"):
    page = context.new_page()
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.add_init_script(f"localStorage.setItem('aether_language', '{language}');")
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page._cmp_errors = errors  # type: ignore[attr-defined]
    url = f"{_state['base_url']}/?surface=companion" + (f"&mode={mode}" if mode else "")
    page.goto(url)
    return page


def test_panel_starts_ready_with_an_honest_empty_state(browser_context, workspace_ready):
    page = _open(browser_context)
    expect(page.get_by_test_id("companion-panel")).to_be_visible(timeout=15000)
    expect(page.get_by_test_id("companion-status-label")).to_have_text("Ready")
    expect(page.get_by_test_id("companion-input")).to_be_focused()
    # No microphone control is offered unless the engine exists; here (headless Chromium) either answer must be consistent.
    has_engine = page.evaluate("!!(window.SpeechRecognition || window.webkitSpeechRecognition)")
    assert (page.get_by_test_id("companion-mic").count() == 1) == has_engine
    # "listening" is never shown by default
    assert page.get_by_test_id("companion-panel").get_attribute("data-status") == "available"
    page.screenshot(path=str(SHOTS / "companion2_panel_empty.png"))
    assert not page._cmp_errors, page._cmp_errors
    page.close()


def test_real_request_without_provider_is_reported_truthfully(browser_context, workspace_ready):
    page = _open(browser_context)
    page.get_by_test_id("companion-input").fill("Hello, who are you?")
    page.get_by_test_id("companion-send").click()
    # the user's message is shown immediately and a loading indicator is visible while the request is in flight
    expect(page.get_by_test_id("companion-msg-user")).to_have_text("Hello, who are you?")
    reply = page.get_by_test_id("companion-msg-assistant").last
    expect(reply).to_contain_text("No AI provider configured", timeout=30000)
    # the runtime said NO_PROVIDER: the status is an error, not a success, and the way out is offered
    expect(page.get_by_test_id("companion-status-label")).to_have_text("Something went wrong")
    expect(page.get_by_test_id("companion-problem")).to_contain_text("No AI provider is set up")
    assert "error" in (reply.get_attribute("class") or "")
    page.screenshot(path=str(SHOTS / "companion2_no_provider_en.png"))
    page.close()


def test_reply_follows_the_ui_language(browser_context, workspace_ready):
    page = _open(browser_context, language="it")
    expect(page.get_by_test_id("companion-status-label")).to_have_text("Pronto")
    page.get_by_test_id("companion-input").fill("Ciao, chi sei?")
    page.get_by_test_id("companion-send").click()
    expect(page.get_by_test_id("companion-msg-assistant").last).to_contain_text("Nessun provider AI configurato", timeout=30000)
    expect(page.get_by_test_id("companion-status-label")).to_have_text("Qualcosa non ha funzionato")
    page.screenshot(path=str(SHOTS / "companion2_no_provider_it.png"))
    page.close()


def test_conversation_is_shared_with_the_main_assistant_session(browser_context, workspace_ready):
    first = _open(browser_context)
    first.get_by_test_id("companion-input").fill("Hello there")
    first.get_by_test_id("companion-send").click()
    expect(first.get_by_test_id("companion-msg-assistant").last).to_be_visible(timeout=30000)
    sid = first.evaluate("localStorage.getItem('aether_active_session_id')")
    assert sid, "the companion must store the session under the key the main Assistant uses"
    first.close()
    second = _open(browser_context)  # a fresh window restores the same session from the runtime
    expect(second.get_by_test_id("companion-msg-user").first).to_be_visible(timeout=15000)
    assert second.evaluate("localStorage.getItem('aether_active_session_id')") == sid
    second.get_by_test_id("companion-new").click()
    expect(second.get_by_test_id("companion-msg-user")).to_have_count(0)
    assert second.evaluate("localStorage.getItem('aether_active_session_id')") is None
    second.close()


def test_orb_panel_transitions_and_keyboard(browser_context, workspace_ready):
    page = _open(browser_context, mode="orb", size=(88, 88))
    orb = page.get_by_test_id("companion-orb")
    expect(orb).to_be_visible(timeout=15000)
    assert orb.get_attribute("data-status") == "available"
    assert page.locator("canvas").count() == 1, "the orb is the real Aether orb engine"
    box = orb.bounding_box()
    assert box and box["width"] <= 88 and box["height"] <= 88
    page.wait_for_timeout(1500)  # let the particle sphere draw
    page.screenshot(path=str(SHOTS / "companion2_orb.png"))
    orb.click()
    expect(page.get_by_test_id("companion-panel")).to_be_visible()
    page.set_viewport_size({"width": 408, "height": 604})
    page.keyboard.press("Escape")
    expect(page.get_by_test_id("companion-orb")).to_be_visible()
    page.get_by_test_id("companion-orb").press("Enter")
    expect(page.get_by_test_id("companion-panel")).to_be_visible()
    page.get_by_test_id("companion-collapse").click()
    expect(page.get_by_test_id("companion-orb")).to_be_visible()
    page.close()


def _mock_overview(page, overview: dict):
    def handler(route):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(overview))
    page.route("**/api/personal/overview*", handler)


def test_pending_approval_drives_status_badge_and_decision(browser_context, workspace_ready):
    """Mocked overview + approval router: verifies the UI's mapping of runtime state and the call it makes."""
    page = browser_context.new_page()
    page.set_viewport_size({"width": 408, "height": 604})
    state = {"pending": [{"execution_id": "exec-1", "title": "Send the weekly report", "description": "Email to the team", "created_at": "2026-01-01T00:00:00Z"}]}
    calls: list[str] = []

    def overview(route):
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"pending_approvals": state["pending"], "background_tasks": []}))

    def approve(route):
        calls.append(route.request.url)
        state["pending"] = []
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"success": True, "status": "approved", "message": "Approved."}))

    page.route("**/api/personal/overview*", overview)
    page.route("**/api/approvals/exec-1/approve", approve)
    page.goto(f"{_state['base_url']}/?surface=companion")
    expect(page.get_by_test_id("companion-status-label")).to_have_text("Needs your approval", timeout=15000)
    expect(page.get_by_test_id("companion-approvals")).to_contain_text("Send the weekly report")
    page.screenshot(path=str(SHOTS / "companion2_approval.png"))
    page.get_by_test_id("companion-approve").click()
    expect(page.get_by_test_id("companion-approvals")).to_have_count(0, timeout=10000)
    assert calls and calls[0].endswith("/api/approvals/exec-1/approve")
    page.close()
    # the orb shows the same fact as a count badge
    orb = browser_context.new_page()
    orb.set_viewport_size({"width": 88, "height": 88})
    orb.route("**/api/personal/overview*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"pending_approvals": [{"execution_id": "e2", "title": "x"}], "background_tasks": []})))
    orb.goto(f"{_state['base_url']}/?surface=companion&mode=orb")
    expect(orb.get_by_test_id("companion-orb")).to_have_attribute("data-status", "awaiting_approval", timeout=15000)
    expect(orb.get_by_test_id("companion-badge")).to_have_text("1")
    orb.close()


def test_running_task_shows_processing_with_progress(browser_context, workspace_ready):
    page = browser_context.new_page()
    page.set_viewport_size({"width": 408, "height": 604})
    page.route("**/api/personal/overview*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(
        {"pending_approvals": [], "background_tasks": [{"id": "t1", "title": "Research competitors", "status": "running", "progress_pct": 40, "current_step": "Reading sources"}]})))
    page.goto(f"{_state['base_url']}/?surface=companion")
    expect(page.get_by_test_id("companion-status-label")).to_have_text("Working on it", timeout=15000)
    expect(page.get_by_test_id("companion-tasks")).to_contain_text("Research competitors")
    expect(page.get_by_test_id("companion-tasks")).to_contain_text("Reading sources")
    page.screenshot(path=str(SHOTS / "companion2_running.png"))
    page.close()


def test_unreachable_runtime_is_reported_not_hidden(browser_context, workspace_ready):
    page = browser_context.new_page()
    page.set_viewport_size({"width": 408, "height": 604})
    page.route("**/api/workspace", lambda r: r.abort())
    page.goto(f"{_state['base_url']}/?surface=companion")
    expect(page.get_by_test_id("companion-problem")).to_contain_text("Cannot reach the Aether runtime", timeout=15000)
    expect(page.get_by_test_id("companion-status-label")).to_have_text("Something went wrong")
    page.close()


@pytest.mark.parametrize("size", [(320, 480), (408, 604), (520, 760)])
def test_panel_layout_has_no_horizontal_overflow(browser_context, workspace_ready, size):
    page = _open(browser_context, size=size)
    expect(page.get_by_test_id("companion-panel")).to_be_visible(timeout=15000)
    o = page.evaluate("({inner: window.innerWidth, doc: document.documentElement.scrollWidth, body: document.body.scrollWidth})")
    assert o["doc"] <= o["inner"] + 1 and o["body"] <= o["inner"] + 1, o
    # the header buttons and the input stay inside the window
    for tid in ("companion-hide", "companion-send", "companion-input"):
        b = page.get_by_test_id(tid).bounding_box()
        assert b and b["x"] >= 0 and b["x"] + b["width"] <= size[0] + 1, (tid, b)
    page.close()


def test_completed_pulse_then_back_to_ready(browser_context, workspace_ready):
    """A successful reply (mocked chat endpoint) shows 'Done' briefly, then the Companion returns to 'Ready'."""
    page = browser_context.new_page()
    page.set_viewport_size({"width": 408, "height": 604})
    page.route("**/api/personal/chat", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(
        {"id": "m1", "session_id": "s-mock", "role": "assistant", "content": "Here you go.", "created_at": "2026-01-01T00:00:00Z", "metadata": {}})))
    page.goto(f"{_state['base_url']}/?surface=companion")
    page.get_by_test_id("companion-input").fill("Say something")
    page.get_by_test_id("companion-send").click()
    expect(page.get_by_test_id("companion-status-label")).to_have_text("Done", timeout=10000)
    expect(page.get_by_test_id("companion-msg-assistant").last).to_have_text("Here you go.")
    expect(page.get_by_test_id("companion-status-label")).to_have_text("Ready", timeout=10000)
    page.close()


def test_listening_status_only_when_the_speech_engine_really_started(browser_context, workspace_ready):
    """A fake SpeechRecognition engine drives onstart/onend: 'Listening' must follow the engine's own events."""
    page = browser_context.new_page()
    page.set_viewport_size({"width": 408, "height": 604})
    page.add_init_script("""
      window.__speech = null;
      const Fake = function () { window.__speech = this; this.start = () => {}; this.stop = () => { this.onend && this.onend(); }; this.abort = () => {}; };
      window.SpeechRecognition = Fake; window.webkitSpeechRecognition = Fake;
    """)
    page.goto(f"{_state['base_url']}/?surface=companion")
    mic = page.get_by_test_id("companion-mic")
    expect(mic).to_be_visible(timeout=15000)
    mic.click()  # asks the engine to start; it has not reported onstart yet
    expect(page.get_by_test_id("companion-status-label")).to_have_text("Ready")
    page.evaluate("window.__speech.onstart && window.__speech.onstart()")
    expect(page.get_by_test_id("companion-status-label")).to_have_text("Listening")
    page.evaluate("window.__speech.onresult({resultIndex: 0, results: [[{transcript: 'hello from the microphone'}]]})")
    expect(page.get_by_test_id("companion-input")).to_have_value("hello from the microphone")
    page.screenshot(path=str(SHOTS / "companion2_listening.png"))
    mic.click()  # stop
    expect(page.get_by_test_id("companion-status-label")).to_have_text("Ready")
    page.close()


def test_orb_gallery_of_real_statuses_at_retina_scale(browser_context, workspace_ready):
    """Screenshots of the orb in every status (for visual review); asserts each status is distinguishable by attribute."""
    ctx = browser_context.browser.new_context(viewport={"width": 88, "height": 88}, device_scale_factor=2, locale="en-US")
    ctx.add_init_script("localStorage.setItem('aether_experience_mode', 'v1');")
    if _state["token"]:
        ctx.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{_state['token']}';")
    scenarios = {
        "available": None,
        "processing": {"pending_approvals": [], "background_tasks": [{"id": "t", "title": "x", "status": "running"}]},
        "awaiting_approval": {"pending_approvals": [{"execution_id": "e", "title": "x"}], "background_tasks": []},
    }
    for name, overview in scenarios.items():
        page = ctx.new_page()
        if overview is not None:
            body = json.dumps(overview)
            page.route("**/api/personal/overview*", lambda route, _request=None, _body=body: route.fulfill(status=200, content_type="application/json", body=_body))
        page.goto(f"{_state['base_url']}/?surface=companion&mode=orb")
        expect(page.get_by_test_id("companion-orb")).to_have_attribute("data-status", name, timeout=15000)
        page.wait_for_timeout(1600)
        page.screenshot(path=str(SHOTS / f"companion2_orb_{name}.png"))
        page.close()
    err = ctx.new_page()
    err.route("**/api/workspace", lambda r: r.abort())
    err.goto(f"{_state['base_url']}/?surface=companion&mode=orb")
    expect(err.get_by_test_id("companion-orb")).to_have_attribute("data-status", "error", timeout=15000)
    err.wait_for_timeout(1200)
    err.screenshot(path=str(SHOTS / "companion2_orb_error.png"))
    ctx.close()


def test_recovers_by_itself_when_the_workspace_appears(browser_context, workspace_ready):
    """Regression (found in the real Tauri window): after 'no workspace' the Companion stayed in error forever."""
    page = browser_context.new_page()
    page.set_viewport_size({"width": 408, "height": 604})
    calls = {"n": 0}

    def workspace(route):
        calls["n"] += 1
        if calls["n"] <= 2:
            route.fulfill(status=503, content_type="application/json", body=json.dumps({"detail": "Workspace not initialized."}))
        else:
            route.continue_()

    page.route("**/api/workspace", workspace)
    page.goto(f"{_state['base_url']}/?surface=companion")
    expect(page.get_by_test_id("companion-problem")).to_contain_text("No workspace is open", timeout=15000)
    expect(page.get_by_test_id("companion-status-label")).to_have_text("Ready", timeout=20000)
    expect(page.get_by_test_id("companion-problem")).to_have_count(0)
    page.close()


# ---------------------------------------------------------------------------------------------------------------------
# Functional parity with the previous Companion: context, files, quick actions, missions, results, proposals, continuity
# ---------------------------------------------------------------------------------------------------------------------

def _json_route(page, pattern: str, body, status: int = 200, method: str | None = None):
    payload = json.dumps(body)

    def handler(route, _request=None):
        if method and route.request.method != method:
            route.continue_()
            return
        route.fulfill(status=status, content_type="application/json", body=payload)

    page.route(pattern, handler)


def test_context_capture_is_explicit_visible_and_usable(browser_context, workspace_ready):
    page = _open(browser_context)
    _json_route(page, "**/api/personal/companion/context", {
        "app_name": "Safari", "window_title": "Quarterly report", "clipboard_text": "Revenue grew 12%", "selected_text": "", "screen_summary": "", "timestamp": "2026-01-01T00:00:00Z"})
    expect(page.get_by_test_id("companion-panel")).to_be_visible(timeout=15000)
    assert page.get_by_test_id("companion-context").count() == 0, "nothing is read until the user asks"
    page.get_by_test_id("companion-capture-context").click()
    card = page.get_by_test_id("companion-context")
    expect(card).to_contain_text("Safari — Quarterly report")
    expect(card).to_contain_text("Revenue grew 12%")
    page.screenshot(path=str(SHOTS / "companion2_context.png"))
    page.get_by_test_id("companion-context-add").click()
    value = page.get_by_test_id("companion-input").input_value()
    assert "Context [Safari - Quarterly report]" in value and "Revenue grew 12%" in value
    expect(page.get_by_test_id("companion-context")).to_have_count(0)
    page.close()


def test_unreadable_context_is_reported_not_invented(browser_context, workspace_ready):
    page = _open(browser_context)
    _json_route(page, "**/api/personal/companion/context", {"app_name": "Desktop", "window_title": "", "clipboard_text": "", "selected_text": "", "screen_summary": "", "timestamp": "t"})
    page.get_by_test_id("companion-capture-context").click()
    expect(page.get_by_test_id("companion-notice")).to_contain_text("Could not read the active window")
    assert page.get_by_test_id("companion-context").count() == 0
    page.close()


def test_real_context_endpoint_yields_either_real_data_or_an_honest_notice(browser_context, workspace_ready):
    page = _open(browser_context)
    expect(page.get_by_test_id("companion-panel")).to_be_visible(timeout=15000)
    page.get_by_test_id("companion-capture-context").click()
    page.wait_for_selector("[data-testid=companion-context], [data-testid=companion-notice]", timeout=15000)
    page.close()


def test_attach_file_goes_to_the_workspace_inbox_through_the_real_api(browser_context, workspace_ready, tmp_path):
    page = _open(browser_context)
    f = tmp_path / "notes.txt"
    f.write_text("hello from a file")
    page.get_by_test_id("companion-file-input").set_input_files(str(f))
    chip = page.get_by_test_id("companion-attachment")
    expect(chip).to_contain_text("notes.txt", timeout=15000)
    assert "inbox" in (chip.get_attribute("title") or ""), "the runtime stored the file in the workspace inbox"
    assert "notes" in page.get_by_test_id("companion-input").input_value(), "the prompt is pre-filled but editable"
    page.screenshot(path=str(SHOTS / "companion2_attachment.png"))
    page.get_by_test_id("companion-attachment").get_by_role("button").click()
    expect(page.get_by_test_id("companion-attachment")).to_have_count(0)
    page.close()


def test_oversized_file_is_refused_before_any_upload(browser_context, workspace_ready):
    page = _open(browser_context)
    uploads: list[str] = []
    page.on("request", lambda r: uploads.append(r.url) if r.url.endswith("/companion/drop") else None)
    page.get_by_test_id("companion-file-input").set_input_files({"name": "huge.bin", "mimeType": "application/octet-stream", "buffer": b"0" * (11 * 1024 * 1024)})
    expect(page.get_by_test_id("companion-notice")).to_contain_text("larger than 10 MB", timeout=15000)
    assert uploads == []
    page.close()


def test_dropping_a_file_shows_the_overlay_and_ingests_it(browser_context, workspace_ready):
    page = _open(browser_context)
    expect(page.get_by_test_id("companion-panel")).to_be_visible(timeout=15000)
    dt = page.evaluate_handle("() => { const d = new DataTransfer(); d.items.add(new File(['dropped text'], 'dropped.md', {type: 'text/markdown'})); return d; }")
    page.dispatch_event("[data-testid=companion-panel]", "dragover", {"dataTransfer": dt})
    expect(page.get_by_test_id("companion-drop-overlay")).to_be_visible()
    page.dispatch_event("[data-testid=companion-panel]", "drop", {"dataTransfer": dt})
    expect(page.get_by_test_id("companion-attachment")).to_contain_text("dropped.md", timeout=15000)
    expect(page.get_by_test_id("companion-drop-overlay")).to_have_count(0)
    page.close()


def test_notifications_quick_action_uses_the_real_runtime(browser_context, workspace_ready):
    page = _open(browser_context)
    page.get_by_test_id("companion-notifications").click()
    card = page.get_by_test_id("companion-notifications-card")
    expect(card).to_be_visible(timeout=15000)
    assert ("unread" in card.inner_text().lower())
    page.close()


def test_notifications_list_unread_items(browser_context, workspace_ready):
    page = _open(browser_context)
    _json_route(page, "**/api/personal/companion/quick-action", {"action": "check_notifications", "status": "completed", "unread_count": 2,
                                                                  "notifications": [{"id": "n1", "title": "Report ready", "message": "Weekly report is done"}, {"id": "n2", "title": "Approval needed", "message": ""}]})
    page.get_by_test_id("companion-notifications").click()
    card = page.get_by_test_id("companion-notifications-card")
    expect(card).to_contain_text("2 unread notifications")
    expect(card).to_contain_text("Report ready")
    page.close()


def test_missions_progress_and_status_come_from_the_runtime(browser_context, workspace_ready):
    page = browser_context.new_page()
    page.set_viewport_size({"width": 408, "height": 604})
    _json_route(page, "**/api/personal/overview*", {"pending_approvals": [], "background_tasks": [], "active_works": [
        {"id": "m1", "title": "Competitor analysis", "status": "running", "current_stage": "Collecting sources", "progress": 35}]})
    page.goto(f"{_state['base_url']}/?surface=companion")
    expect(page.get_by_test_id("companion-status-label")).to_have_text("Working on it", timeout=15000)
    card = page.get_by_test_id("companion-mission")
    expect(card).to_contain_text("Competitor analysis")
    expect(card).to_contain_text("Collecting sources")
    page.screenshot(path=str(SHOTS / "companion2_mission.png"))
    page.close()


def test_a_pending_mission_is_listed_but_is_not_work_in_progress(browser_context, workspace_ready):
    page = browser_context.new_page()
    page.set_viewport_size({"width": 408, "height": 604})
    _json_route(page, "**/api/personal/overview*", {"pending_approvals": [], "background_tasks": [], "active_works": [{"id": "m2", "title": "Not started yet", "status": "pending"}]})
    page.goto(f"{_state['base_url']}/?surface=companion")
    expect(page.get_by_test_id("companion-mission")).to_contain_text("Not started yet", timeout=15000)
    expect(page.get_by_test_id("companion-status-label")).to_have_text("Ready")
    page.close()


def test_results_are_listed_and_collapsible(browser_context, workspace_ready):
    page = browser_context.new_page()
    page.set_viewport_size({"width": 408, "height": 604})
    _json_route(page, "**/api/personal/overview*", {"pending_approvals": [], "background_tasks": [], "recent_deliverables": [
        {"id": "d1", "title": "report.md", "source": "Mission", "file_path": "/ws/deliverables/report.md", "file_type": ".md", "file_size_bytes": 4096},
        {"id": "d2", "title": "data.csv", "source": "Files", "file_path": "/ws/files/data.csv", "file_type": ".csv", "file_size_bytes": 100}]})
    page.goto(f"{_state['base_url']}/?surface=companion")
    toggle = page.get_by_test_id("companion-results-toggle")
    expect(toggle).to_contain_text("Recent results (2)", timeout=15000)
    assert page.get_by_test_id("companion-result").count() == 0
    toggle.click()
    expect(page.get_by_test_id("companion-result")).to_have_count(2)
    expect(page.get_by_test_id("companion-result").first).to_contain_text("4 KB")
    page.screenshot(path=str(SHOTS / "companion2_results.png"))
    toggle.click()
    expect(page.get_by_test_id("companion-result")).to_have_count(0)
    page.close()


def test_a_proposal_is_shown_truthfully_without_pretending_to_accept_it(browser_context, workspace_ready):
    page = browser_context.new_page()
    page.set_viewport_size({"width": 408, "height": 604})
    _json_route(page, "**/api/personal/chat", {"id": "m9", "session_id": "s-p", "role": "assistant", "content": "I can do this. Shall I proceed?", "created_at": "2026-01-01T00:00:00Z",
                                               "metadata": {"proposal_id": "prop-1", "proposal": {"id": "prop-1", "title": "Write the Q3 summary", "objective": "Write the Q3 summary", "status": "pending"}}})
    page.goto(f"{_state['base_url']}/?surface=companion")
    page.get_by_test_id("companion-input").fill("Write the Q3 summary")
    page.get_by_test_id("companion-send").click()
    card = page.get_by_test_id("companion-proposal")
    expect(card).to_contain_text("waiting for your confirmation", timeout=15000)
    expect(card).to_contain_text("Write the Q3 summary")
    expect(card.get_by_role("button")).to_have_text("Review in Aether")
    assert page.get_by_test_id("companion-approve").count() == 0, "accepting a proposal is not offered here"
    page.screenshot(path=str(SHOTS / "companion2_proposal.png"))
    page.close()


def test_approval_uses_the_runtime_human_summary(browser_context, workspace_ready):
    page = browser_context.new_page()
    page.set_viewport_size({"width": 408, "height": 604})
    _json_route(page, "**/api/personal/overview*", {"background_tasks": [], "pending_approvals": [{"execution_id": "e1", "action_name": "email.send", "description": "Send an email", "human_summary": 'Send email to "anna@example.com"'}]})
    page.goto(f"{_state['base_url']}/?surface=companion")
    expect(page.get_by_test_id("companion-approvals")).to_contain_text('Send email to "anna@example.com"', timeout=15000)
    page.close()


def test_a_conversation_started_in_the_main_assistant_continues_in_the_companion(browser_context, workspace_ready):
    main = browser_context.new_page()
    main.goto(_state["base_url"])
    main.wait_for_selector(".sidebar", timeout=15000)
    ws_name = main.evaluate("fetch('/api/workspace').then(r => r.json()).then(d => d.name)")
    reply = main.evaluate("""async (ws) => {
        const r = await fetch('/api/personal/chat', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Aether-Session-Token': window.__AETHER_SESSION_TOKEN__ || ''},
          body: JSON.stringify({prompt: 'Message written in the main assistant', workspace_id: ws, language: 'en'})});
        return r.json();
    }""", ws_name)
    sid = reply["session_id"]
    main.evaluate("(sid) => localStorage.setItem('aether_active_session_id', sid)", sid)
    comp = _open(browser_context)
    expect(comp.get_by_test_id("companion-msg-user").first).to_have_text("Message written in the main assistant", timeout=15000)
    comp.get_by_test_id("companion-input").fill("And a follow-up from the companion")
    comp.get_by_test_id("companion-send").click()
    expect(comp.get_by_test_id("companion-msg-assistant").last).to_be_visible(timeout=30000)
    assert comp.evaluate("localStorage.getItem('aether_active_session_id')") == sid, "same session id, not a new one"
    comp.close()
    main.close()


def test_keyboard_shortcuts_new_conversation(browser_context, workspace_ready):
    page = _open(browser_context)
    page.get_by_test_id("companion-input").fill("Hello")
    page.get_by_test_id("companion-send").click()
    expect(page.get_by_test_id("companion-msg-assistant").last).to_be_visible(timeout=30000)
    page.keyboard.press("Control+k")
    expect(page.get_by_test_id("companion-msg-user")).to_have_count(0)
    page.close()


def test_layout_with_all_recovered_sections_stays_inside_the_window(browser_context, workspace_ready):
    page = browser_context.new_page()
    page.set_viewport_size({"width": 408, "height": 604})
    _json_route(page, "**/api/personal/overview*", {
        "pending_approvals": [{"execution_id": "e1", "human_summary": "Send email to anna"}],
        "background_tasks": [{"id": "t1", "title": "Research", "status": "running", "progress_pct": 50}],
        "active_works": [{"id": "m1", "title": "Mission", "status": "running", "progress": 20}],
        "recent_deliverables": [{"id": "d1", "title": "report.md", "source": "Mission", "file_path": "/x/report.md", "file_type": ".md", "file_size_bytes": 10}]})
    _json_route(page, "**/api/personal/companion/context", {"app_name": "Safari", "window_title": "T", "clipboard_text": "x", "timestamp": "t"})
    page.goto(f"{_state['base_url']}/?surface=companion")
    expect(page.get_by_test_id("companion-approvals")).to_be_visible(timeout=15000)
    page.get_by_test_id("companion-capture-context").click()
    page.get_by_test_id("companion-results-toggle").click()
    o = page.evaluate("({inner: window.innerWidth, doc: document.documentElement.scrollWidth, ih: window.innerHeight, dh: document.documentElement.scrollHeight})")
    assert o["doc"] <= o["inner"] + 1, o
    for tid in ("companion-input", "companion-send", "companion-attach", "companion-capture-context", "companion-hide"):
        b = page.get_by_test_id(tid).bounding_box()
        assert b and 0 <= b["x"] and b["x"] + b["width"] <= 409 and 0 <= b["y"] and b["y"] + b["height"] <= 605, (tid, b)
    page.screenshot(path=str(SHOTS / "companion2_full_sections.png"))
    page.close()
