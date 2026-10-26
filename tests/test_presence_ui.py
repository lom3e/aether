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
        # the daily spoken brief is tested on its own; elsewhere it counts as already given today
        context.add_init_script("localStorage.setItem('aether_brief_day', new Date().toISOString().slice(0, 10)); localStorage.setItem('aether_met', '1'); localStorage.setItem('aether_greet_aloud', '0');")
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
        {"id": "pm-1", "status": "new", "kind": "i_promised", "title": "Send the quote", "who": "Mario Rossi", "due_at": 4102444800, "message_id": "s1", "subject": "Re: website"},
        {"id": "pm-2", "status": "new", "kind": "they_promised", "title": "Send the October invoice", "who": "Laura Bianchi", "due_at": None, "message_id": "r1", "subject": "Invoice"}],
        "fulfilled": [{"id": "pm-3", "status": "new", "kind": "fulfilled", "title": "Logo for Verdi", "who": "Verdi", "due_at": None, "message_id": "s2", "subject": "Logo", "job_id": "jb-1"}]}
    offers: list = []
    page.route("**/api/life/promises/scan", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(scan)))
    page.route("**/api/presence/offer", lambda r: (offers.append(r.request.post_data_json), r.fulfill(status=200, content_type="application/json", body=json.dumps({"text": "ok"})))[1])
    page.goto(_state["base_url"])
    page.evaluate("localStorage.setItem('aether_home_view', 'presence')")
    page.reload()
    page.get_by_test_id("presence-open-promises").click()
    items = page.get_by_test_id("promise-item")
    expect(items).to_have_count(3)
    expect(items.first).to_contain_text("Looks done")
    expect(items.nth(1)).to_contain_text("You promised Mario Rossi")
    expect(items.nth(2)).to_contain_text("Laura Bianchi promised you")
    items.nth(1).get_by_test_id("promise-save").click()
    expect(items.nth(1)).to_contain_text("Tracked")
    items.first.get_by_test_id("promise-save").click()
    expect(items.first).to_contain_text("Done")
    assert [(o["offer"]["type"], o["offer"]["promise_id"], o["answer"]) for o in offers] == [("track", "pm-1", "yes"), ("job_done", "pm-3", "yes")]
    page.get_by_test_id("promise-watch-on").click()
    expect(page.get_by_test_id("promises")).to_contain_text("every day")
    assert offers[-1]["offer"] == {"type": "watch_on"}
    page.close()


def test_the_orb_speaks_first_once_a_day_and_a_short_yes_answers_its_question(browser_context):
    page = browser_context.new_page()
    page.add_init_script("localStorage.removeItem('aether_brief_day'); localStorage.setItem('aether_home_view', 'presence');")
    brief = {"text": "Good morning. You promised Laura: “Send the photos”, by tomorrow. Want me to draft the email?",
             "body": "You promised Laura: “Send the photos”, by tomorrow. Want me to draft the email?",
             "offer": {"type": "ask", "promise_id": "pm-9", "prompt": "Draft a reply to Laura about the email “Photos”: Send the photos."}}
    offers: list = []
    chats: list = []
    page.route("**/api/presence/brief*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(brief)))
    page.route("**/api/presence/offer", lambda r: (offers.append(r.request.post_data_json), r.fulfill(status=200, content_type="application/json",
                                                                                                    body=json.dumps({"text": "", "prompt": brief["offer"]["prompt"]})))[1])
    page.route("**/api/personal/chat", lambda r: (chats.append(r.request.post_data_json), r.fulfill(status=200, content_type="application/json", body=json.dumps(
        {"id": "a1", "role": "assistant", "content": "Here is the draft for Laura.", "session_id": "s-1", "steps": [], "created_at": "2099-01-01T00:00:00Z"})))[1])
    page.goto(_state["base_url"])
    card = page.get_by_test_id("presence-brief")
    expect(card).to_contain_text("You promised Laura")
    expect(card.get_by_role("heading", level=1)).to_contain_text("Good")
    expect(page.get_by_test_id("brief-yes")).to_be_visible()
    box = page.get_by_test_id("presence").get_by_role("textbox")
    box.fill("yes")
    box.press("Enter")
    expect(page.get_by_test_id("presence-answer")).to_contain_text("Here is the draft for Laura.")
    assert offers == [{"offer": brief["offer"], "answer": "yes", "language": "en"}]
    assert [c["prompt"] for c in chats] == [brief["offer"]["prompt"]], "the short yes is not sent as a message: the offer is"
    page.reload()
    expect(page.get_by_test_id("presence-brief")).to_have_count(0)  # once a day
    page.close()


def test_the_sidebar_shows_few_things_and_advanced_tools_only_on_request(browser_context):
    page = browser_context.new_page()
    page.goto(_state["base_url"])
    expect(page.get_by_test_id("presence")).to_be_visible(timeout=20000)
    for visible in ("nav-home", "nav-people", "nav-connections", "nav-privacy", "nav-settings"):
        expect(page.get_by_test_id(visible).first).to_be_visible()
    for hidden in ("nav-missions", "nav-memory", "nav-advanced"):
        expect(page.get_by_test_id(hidden).first).to_be_hidden()
    page.get_by_test_id("nav-settings").first.click()
    page.get_by_role("tab", name="General").click()
    page.get_by_test_id("advanced-tools-toggle").check()
    expect(page.get_by_test_id("nav-missions").first).to_be_visible()
    expect(page.get_by_test_id("nav-advanced")).to_be_visible()
    page.get_by_test_id("advanced-tools-toggle").uncheck()
    expect(page.get_by_test_id("nav-advanced")).to_have_count(0)
    page.close()


def _voice_status(natural_state: str, done: int = 0, engine: str = "system") -> dict:
    return {"settings": {"stt": "auto", "tts": "auto", "system_voice": "", "openai_voice": "coral", "neural_voice": ""},
            "stt": {"engine": "device", "available": ["device"], "model": ""},
            "tts": {"engine": engine, "available": ["neural"] if natural_state == "ready" else [],
                    "voice": "af_heart" if engine == "neural" else "", "quality": "natural" if engine == "neural" else "none",
                    "voices": [], "openai_voices": [], "needs_better_voice": engine == "device",
                    "neural": {"state": natural_state, "voices": [{"id": "af_heart", "name": "Heart"}, {"id": "am_michael", "name": "Michael"}],
                               "download": {"state": natural_state, "done": done, "total": 1000, "error": ""}, "size_mb": 121}}}


def test_the_natural_voice_is_downloaded_once_with_progress_then_offered_as_the_voice(browser_context):
    """Voice status and download routes mocked: they exercise the Settings flow, the model itself is tested in test_neural_voice."""
    page = browser_context.new_page()
    phase = {"state": "missing", "polls": 0}
    calls: list[str] = []

    def status(route):
        if phase["state"] == "downloading":
            phase["polls"] += 1
            if phase["polls"] > 2:
                phase["state"] = "ready"
        st = phase["state"]
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(_voice_status(st, done=400 if st == "downloading" else 0, engine="neural" if st == "ready" else "device")))

    def download(route):
        calls.append("download")
        phase["state"] = "downloading"
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"state": "downloading", "done": 0, "total": 1000, "error": ""}))

    page.route("**/api/voice/status*", status)
    page.route("**/api/voice/natural/download", download)
    page.goto(_state["base_url"])
    page.get_by_test_id("nav-settings").first.click()
    page.get_by_role("tab", name="General").click()
    card = page.get_by_test_id("voice-natural")
    expect(card).to_be_visible(timeout=15000)
    expect(card).to_contain_text("121 MB")
    expect(page.get_by_test_id("voice-better")).to_have_count(0)  # one suggestion at a time: the natural voice
    page.get_by_test_id("voice-natural-download").click()
    expect(page.get_by_test_id("voice-natural-progress")).to_be_visible()
    expect(card).to_contain_text("40%")
    expect(card).to_have_count(0, timeout=10000)  # done: the card goes away
    assert calls == ["download"]
    options = page.get_by_test_id("voice-tts").locator("option").all_inner_texts()
    assert options[:2] == ["Heart · natural", "Michael · natural"]
    expect(page.get_by_test_id("voice-tts")).to_have_value("neural:af_heart")
    expect(page.get_by_test_id("voice-natural-remove")).to_be_visible()

    # "Prova la voce" plays the audio as a decoded Web Audio buffer (WebKit can silence a media element routed into Web Audio)
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b"\x00\x10" * 2400)
    page.route("**/api/voice/speak", lambda route: route.fulfill(status=200, content_type="audio/wav", body=buf.getvalue()))
    page.evaluate("""() => { window.__played = 0; const s = AudioBufferSourceNode.prototype.start;
        AudioBufferSourceNode.prototype.start = function (...a) { window.__played++; return s.apply(this, a); }; }""")
    page.get_by_test_id("voice-try").click()
    page.wait_for_function("window.__played > 0", timeout=5000)
    page.close()
