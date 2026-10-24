"""
Screen understanding in the Companion panel, in a real browser against a real Aether server (isolated data dir).

The native capture (src-tauri/src/screen_capture.rs) is replaced here by a stub of the Tauri IPC layer, because a browser
cannot capture the desktop; the real native capture is verified separately on the packaged app. The vision route is
mocked with page.route() only where a vision-capable provider is needed (the test server has no provider); the
"no provider" case runs against the real runtime.
"""
from __future__ import annotations

import base64
import json
import os
import struct
import tempfile
import zlib
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from test_personal_agent_ui import _ensure_workspace

_state: dict = {}
SHOTS = Path(os.environ.get("AETHER_TEST_SCREENSHOTS_DIR") or tempfile.gettempdir()) / "aether-test-screenshots"


def _png_b64(w: int = 320, h: int = 200) -> str:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + b"".join(bytes((x * 255 // w, y * 255 // h, 140)) for x in range(w)) for y in range(h))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    return base64.b64encode(png).decode()


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


@pytest.fixture(scope="module")
def workspace_ready(browser_context):
    import test_personal_agent_ui as base

    base._state.update(_state)
    page = browser_context.new_page()
    _ensure_workspace(page)
    page.close()


def _stub(permission: str = "granted", capture: dict | None = None, supported: bool = True) -> str:
    """A stand-in for the Tauri IPC layer: records every native call in window.__native_calls."""
    cap = capture if capture is not None else {"ok": True, "image_base64": _png_b64(), "media_type": "image/png", "width": 320, "height": 200,
                                                "screen": {"x": 0, "y": 0, "width": 1440, "height": 900}}
    return f"""
    window.__native_calls = [];
    window.__perm = {json.dumps(permission)};
    window.__capture = {json.dumps(cap)};
    window.__TAURI_INTERNALS__ = {{
      transformCallback: () => 0,
      invoke: async (cmd, args) => {{
        window.__native_calls.push([cmd, args || null]);
        if (cmd === 'screen_capture_status') return {{platform: 'macos', supported: {json.dumps(supported)}, permission: window.__perm}};
        if (cmd === 'screen_capture_request_permission') return {{platform: 'macos', supported: {json.dumps(supported)}, permission: window.__perm}};
        if (cmd === 'screen_capture_take') return window.__capture;
        if (cmd === 'companion_take_context') {{ const c = window.__summon || null; window.__summon = null; return c; }}
        return null;
      }},
    }};
    """


def _open(context, stub: str, language: str = "en"):
    page = context.new_page()
    page.set_viewport_size({"width": 408, "height": 604})
    page.add_init_script(f"localStorage.setItem('aether_language', '{language}');")
    page.add_init_script(stub)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page._errors = errors  # type: ignore[attr-defined]
    page.goto(f"{_state['base_url']}/?surface=companion")
    expect(page.get_by_test_id("companion-panel")).to_be_visible(timeout=15000)
    return page


def _mock_vision(page, *, supported=True, reason="ok", reply=None, status_code=200, record=None):
    status = {"supported": supported, "reason": reason, "provider": "groq", "model": "meta-llama/llama-4-scout-17b-16e-instruct" if supported else "llama-3.3-70b-versatile", "max_image_bytes": 8388608}
    page.route("**/api/personal/companion/vision/status", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(status)))

    def handle(route):
        if record is not None:
            record.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=status_code, content_type="application/json", body=json.dumps(reply if reply is not None else {}))

    page.route("**/api/personal/companion/vision", handle)


OK_REPLY = {
    "status": "ok", "reason": "", "detail": "", "provider": "groq", "model": "meta-llama/llama-4-scout-17b-16e-instruct",
    "message": {"id": "msg-vision-1", "session_id": "sess-vision-1", "role": "assistant", "content": "This is a **colour gradient** test image.", "metadata": {}, "created_at": "2026-01-01T00:00:00Z"},
    "annotations": [
        {"kind": "box", "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.25, "label": "Gradient start"},
        {"kind": "point", "x": 0.8, "y": 0.7, "label": "Far end"},
        {"kind": "box", "x": 1.6, "y": 0.2, "w": 0.3, "h": 0.25, "label": "Out of range"},  # must never be drawn
    ],
    "annotations_rejected": [{"index": "2", "reason": "out_of_bounds"}], "annotation_requested": True,
}


def test_nothing_is_captured_until_the_user_chooses(browser_context, workspace_ready):
    page = _open(browser_context, _stub())
    _mock_vision(page)
    page.get_by_test_id("companion-vision-open").click()
    expect(page.get_by_test_id("vision-capture-screen")).to_be_enabled(timeout=10000)
    cmds = [c[0] for c in page.evaluate("window.__native_calls")]
    assert "screen_capture_take" not in cmds, "opening the flow must not capture anything"
    page.get_by_test_id("vision-close").click()
    assert "screen_capture_take" not in [c[0] for c in page.evaluate("window.__native_calls")]
    assert not page._errors, page._errors
    page.close()


def test_capture_preview_marks_and_answer_with_validated_annotations(browser_context, workspace_ready):
    page = _open(browser_context, _stub())
    sent: list = []
    _mock_vision(page, reply=OK_REPLY, record=sent)
    page.get_by_test_id("companion-vision-open").click()
    page.get_by_test_id("vision-capture-screen").click()
    preview = page.get_by_test_id("vision-preview")
    expect(preview).to_be_visible(timeout=10000)
    assert ["screen_capture_take", {"mode": "screen"}] in page.evaluate("window.__native_calls")
    expect(page.get_by_test_id("vision-sent-to")).to_contain_text("llama-4-scout")
    assert sent == [], "nothing is sent before the user presses Send"
    page.screenshot(path=str(SHOTS / "companion_vision_review.png"))

    # draw a box with the mouse on the preview
    b = preview.bounding_box()
    assert abs(b["width"] / b["height"] - 320 / 200) < 0.02, "the drawing surface is exactly the image (no letterbox), so marks land where they are drawn"
    page.mouse.move(b["x"] + b["width"] * 0.2, b["y"] + b["height"] * 0.2)
    page.mouse.down()
    page.mouse.move(b["x"] + b["width"] * 0.5, b["y"] + b["height"] * 0.6, steps=6)
    page.mouse.up()
    expect(page.get_by_test_id("vision-mark-count")).to_have_text("1 mark(s)")
    page.get_by_test_id("vision-tool-arrow").click()
    page.mouse.move(b["x"] + b["width"] * 0.7, b["y"] + b["height"] * 0.8)
    page.mouse.down()
    page.mouse.move(b["x"] + b["width"] * 0.9, b["y"] + b["height"] * 0.3, steps=6)
    page.mouse.up()
    expect(page.get_by_test_id("vision-mark-count")).to_have_text("2 mark(s)")
    page.get_by_test_id("vision-undo").click()
    expect(page.get_by_test_id("vision-mark-count")).to_have_text("1 mark(s)")
    # a click without a drag draws nothing
    page.mouse.click(b["x"] + 40, b["y"] + 40)
    expect(page.get_by_test_id("vision-mark-count")).to_have_text("1 mark(s)")

    page.get_by_test_id("vision-prompt").fill("Explain the marked area")
    page.get_by_test_id("vision-annotate").check()
    page.get_by_test_id("vision-send").click()
    expect(page.get_by_test_id("companion-msg-assistant").last).to_contain_text("colour gradient", timeout=10000)
    assert len(sent) == 1
    req = sent[0]
    assert req["prompt"] == "Explain the marked area" and req["annotate"] is True and req["language"] == "en"
    raw = base64.b64decode(req["image_base64"])
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert req["image_base64"] != _png_b64(), "the user's marks are drawn into the image that is sent"

    # the conversation shows the image; only the two valid model marks are drawn, the out-of-range one never is
    expect(page.get_by_test_id("companion-msg-image")).to_have_count(2)
    last = page.get_by_test_id("companion-msg-assistant").last
    expect(last.get_by_test_id("vision-shape-label")).to_have_count(2)  # the box label and the point label
    labels = [x.inner_text() for x in last.get_by_test_id("vision-shape-label").all()]
    assert "Out of range" not in labels
    expect(last.get_by_test_id("vision-shape-point")).to_have_count(1)
    expect(page.get_by_test_id("companion-model-marks")).to_be_visible()
    expect(page.get_by_test_id("companion-vision")).to_have_count(0)  # the flow closed itself
    assert page.evaluate("localStorage.getItem('aether_active_session_id')") == "sess-vision-1", "same session key as the main assistant"
    page.screenshot(path=str(SHOTS / "companion_vision_answer.png"))
    assert not page._errors, page._errors
    page.close()


def test_permission_denied_explains_how_to_enable_it_and_captures_nothing(browser_context, workspace_ready):
    page = _open(browser_context, _stub(permission="denied"))
    _mock_vision(page)
    page.get_by_test_id("companion-vision-open").click()
    expect(page.get_by_test_id("vision-permission")).to_contain_text("Screen & System Audio Recording", timeout=10000)
    page.get_by_test_id("vision-capture-screen").click()
    expect(page.get_by_test_id("vision-permission")).to_be_visible()
    calls = [c[0] for c in page.evaluate("window.__native_calls")]
    assert "screen_capture_request_permission" in calls and "screen_capture_take" not in calls
    page.get_by_test_id("vision-open-settings").click()
    assert "screen_capture_open_settings" in [c[0] for c in page.evaluate("window.__native_calls")]
    page.screenshot(path=str(SHOTS / "companion_vision_permission.png"))
    page.close()


def test_native_denial_after_the_check_is_handled(browser_context, workspace_ready):
    page = _open(browser_context, _stub(capture={"ok": False, "error": "permission_denied", "detail": "x"}))
    _mock_vision(page)
    page.get_by_test_id("companion-vision-open").click()
    page.get_by_test_id("vision-capture-region").click()
    expect(page.get_by_test_id("vision-permission")).to_be_visible(timeout=10000)
    assert page.get_by_test_id("vision-preview").count() == 0
    page.close()


@pytest.mark.parametrize("cap,expected", [
    ({"ok": False, "error": "cancelled", "detail": ""}, "Nothing was captured"),
    ({"ok": False, "error": "capture_failed", "detail": "no display"}, "no display"),
    ({"ok": False, "error": "too_large", "detail": ""}, "too large"),
])
def test_cancelled_failed_or_oversized_captures_never_reach_the_preview(browser_context, workspace_ready, cap, expected):
    page = _open(browser_context, _stub(capture=cap))
    _mock_vision(page)
    page.get_by_test_id("companion-vision-open").click()
    page.get_by_test_id("vision-capture-region").click()
    expect(page.get_by_test_id("vision-note")).to_contain_text(expected, timeout=10000)
    assert page.get_by_test_id("vision-preview").count() == 0
    page.close()


def test_a_model_without_vision_blocks_the_capture_and_says_why(browser_context, workspace_ready):
    page = _open(browser_context, _stub())
    _mock_vision(page, supported=False, reason="model_without_vision")
    page.get_by_test_id("companion-vision-open").click()
    expect(page.get_by_test_id("vision-unavailable")).to_contain_text("llama-3.3-70b-versatile", timeout=10000)
    expect(page.get_by_test_id("vision-capture-screen")).to_be_disabled()
    assert "screen_capture_take" not in [c[0] for c in page.evaluate("window.__native_calls")]
    page.close()


def test_without_any_provider_the_real_runtime_reports_it(browser_context, workspace_ready):
    """No mocks on the vision routes: the test server really has no provider configured."""
    page = _open(browser_context, _stub())
    page.get_by_test_id("companion-vision-open").click()
    expect(page.get_by_test_id("vision-unavailable")).to_contain_text("No AI provider is configured", timeout=10000)
    expect(page.get_by_test_id("vision-capture-screen")).to_be_disabled()
    page.close()


def test_unsupported_platform_is_reported_not_faked(browser_context, workspace_ready):
    page = _open(browser_context, _stub(permission="unsupported", supported=False))
    _mock_vision(page)
    page.get_by_test_id("companion-vision-open").click()
    expect(page.get_by_test_id("vision-platform")).to_be_visible(timeout=10000)
    expect(page.get_by_test_id("vision-capture-screen")).to_be_disabled()
    page.close()


@pytest.mark.parametrize("reply,status_code,expected", [
    ({"status": "failed", "reason": "timeout", "detail": ""}, 200, "took too long"),
    ({"status": "failed", "reason": "auth", "detail": ""}, 200, "rejected the credentials"),
    ({"status": "failed", "reason": "empty_response", "detail": ""}, 200, "empty answer"),
    ({"status": "unavailable", "reason": "model_without_vision", "detail": "", "model": "text-only"}, 200, "text-only"),
    ({"detail": {"code": "unsupported_format", "message": "x"}}, 422, "rejected"),
])
def test_analysis_errors_are_shown_and_nothing_is_added_to_the_conversation(browser_context, workspace_ready, reply, status_code, expected):
    page = _open(browser_context, _stub())
    _mock_vision(page, reply=reply, status_code=status_code)
    page.get_by_test_id("companion-vision-open").click()
    page.get_by_test_id("vision-capture-screen").click()
    expect(page.get_by_test_id("vision-preview")).to_be_visible(timeout=10000)
    page.get_by_test_id("vision-send").click()
    expect(page.get_by_test_id("vision-error")).to_contain_text(expected, timeout=10000)
    assert page.get_by_test_id("companion-msg-user").count() == 0 and page.get_by_test_id("companion-msg-assistant").count() == 0
    # the preview is still there, so the user can retry or discard
    expect(page.get_by_test_id("vision-preview")).to_be_visible()
    page.get_by_test_id("vision-discard").click()
    expect(page.get_by_test_id("companion-vision")).to_have_count(0)
    page.close()


def test_escape_discards_the_image_without_collapsing_the_panel(browser_context, workspace_ready):
    page = _open(browser_context, _stub())
    _mock_vision(page)
    page.get_by_test_id("companion-vision-open").click()
    page.get_by_test_id("vision-capture-screen").click()
    expect(page.get_by_test_id("vision-preview")).to_be_visible(timeout=10000)
    page.keyboard.press("Escape")
    expect(page.get_by_test_id("companion-vision")).to_have_count(0)
    expect(page.get_by_test_id("companion-panel")).to_be_visible()
    page.get_by_test_id("companion-vision-open").click()
    assert page.get_by_test_id("vision-preview").count() == 0, "a discarded capture does not come back"
    page.close()


def test_italian_ui(browser_context, workspace_ready):
    page = _open(browser_context, _stub(permission="denied"), language="it")
    _mock_vision(page)
    page.get_by_test_id("companion-vision-open").click()
    expect(page.get_by_test_id("vision-permission")).to_contain_text("Registrazione schermo", timeout=10000)
    expect(page.get_by_test_id("vision-capture-screen")).to_contain_text("Schermo intero")
    page.close()


def test_remember_this_screen_sends_one_explicit_request_and_closes(browser_context, workspace_ready):
    page = _open(browser_context, _stub())
    _mock_vision(page)
    kept: list = []
    page.route("**/api/personal/companion/vision/remember", lambda r: (kept.append(json.loads(r.request.post_data or "{}")), r.fulfill(status=200, content_type="application/json", body=json.dumps({"status": "ok", "item": {"id": "scr-1"}})))[1])
    page.get_by_test_id("companion-vision-open").click()
    page.get_by_test_id("vision-capture-screen").click()
    expect(page.get_by_test_id("vision-preview")).to_be_visible(timeout=10000)
    assert kept == [], "nothing is kept until the user chooses a duration"
    page.get_by_test_id("vision-remember-30").click()
    expect(page.get_by_test_id("companion-vision")).to_have_count(0, timeout=10000)
    assert len(kept) == 1 and kept[0]["ttl_days"] == 30
    assert base64.b64decode(kept[0]["image_base64"])[:4] == b"\x89PNG"
    assert not page._errors, page._errors
    page.close()


def test_a_blurred_area_is_destroyed_in_the_image_that_is_sent(browser_context, workspace_ready):
    page = _open(browser_context, _stub())
    sent: list = []
    _mock_vision(page, reply=OK_REPLY, record=sent)
    page.get_by_test_id("companion-vision-open").click()
    page.get_by_test_id("vision-capture-screen").click()
    preview = page.get_by_test_id("vision-preview")
    expect(preview).to_be_visible(timeout=10000)
    page.get_by_test_id("vision-tool-blur").click()
    b = preview.bounding_box()
    page.mouse.move(b["x"] + b["width"] * 0.1, b["y"] + b["height"] * 0.1)
    page.mouse.down()
    page.mouse.move(b["x"] + b["width"] * 0.5, b["y"] + b["height"] * 0.5, steps=6)
    page.mouse.up()
    expect(page.get_by_test_id("vision-mark-count")).to_have_text("1 mark(s)")
    page.get_by_test_id("vision-prompt").fill("What is here?")
    page.get_by_test_id("vision-send").click()
    expect(page.get_by_test_id("companion-msg-assistant").last).to_contain_text("colour gradient", timeout=10000)
    assert len(sent) == 1

    def pixels(b64):  # (inside the blurred area, outside it) as RGB sums, read back through a canvas
        return page.evaluate("""async (b64) => {
            const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
            const c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight;
            const x = c.getContext('2d'); x.drawImage(img, 0, 0);
            const at = (fx, fy) => { const d = x.getImageData(Math.floor(c.width * fx), Math.floor(c.height * fy), 1, 1).data; return d[0] + d[1] + d[2]; };
            return [at(0.3, 0.3), at(0.8, 0.8)];
        }""", b64)

    before_in, before_out = pixels(_png_b64())
    after_in, after_out = pixels(sent[0]["image_base64"])
    assert after_out == before_out, "outside the blurred area the image is untouched"
    assert after_in < before_in * 0.7, "inside it the original pixels are replaced"
    page.close()


def _ocr_capture():
    """A capture whose local OCR (stubbed; the real helper's output shape) found an IBAN in the middle of the image."""
    words = [{"text": "Fattura", "x": 0.05, "y": 0.1, "w": 0.15, "h": 0.1},
             {"text": "IT60X0542811101000000123456", "x": 0.25, "y": 0.45, "w": 0.5, "h": 0.1}]
    return {"ok": True, "image_base64": _png_b64(), "media_type": "image/png", "width": 320, "height": 200,
            "screen": {"x": 0, "y": 0, "width": 1440, "height": 900}, "ocr": {"width": 320, "height": 200, "words": words}}


def _read_pixel(page, b64, fx, fy):
    return page.evaluate("""async ([b64, fx, fy]) => {
        const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
        const c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight;
        const x = c.getContext('2d'); x.drawImage(img, 0, 0);
        const d = x.getImageData(Math.floor(c.width * fx), Math.floor(c.height * fy), 1, 1).data; return d[0] + d[1] + d[2];
    }""", [b64, fx, fy])


def test_screen_shield_hides_sensitive_text_before_the_image_is_sent_and_can_be_shown(browser_context, workspace_ready):
    # The OCR output is stubbed (the native helper is verified separately); the shield route is the real server's.
    page = _open(browser_context, _stub(capture=_ocr_capture()))
    sent: list = []
    _mock_vision(page, reply=OK_REPLY, record=sent)
    page.get_by_test_id("companion-vision-open").click()
    page.get_by_test_id("vision-capture-screen").click()
    expect(page.get_by_test_id("vision-preview")).to_be_visible(timeout=10000)
    shield = page.get_by_test_id("vision-shield")
    expect(shield).to_have_attribute("data-state", "hidden", timeout=10000)
    expect(shield).to_contain_text("Hidden before sending: 1 area(s) (iban)")
    expect(page.get_by_test_id("vision-mark-count")).to_have_text("", timeout=2000)  # automatic areas are not the user's marks
    page.get_by_test_id("vision-prompt").fill("What is this?")
    page.get_by_test_id("vision-send").click()
    expect(page.get_by_test_id("companion-msg-assistant").last).to_contain_text("colour gradient", timeout=10000)
    assert len(sent) == 1
    before_in, before_out = _read_pixel(page, _png_b64(), 0.5, 0.5), _read_pixel(page, _png_b64(), 0.1, 0.9)
    after_in, after_out = _read_pixel(page, sent[0]["image_base64"], 0.5, 0.5), _read_pixel(page, sent[0]["image_base64"], 0.1, 0.9)
    assert after_out == before_out and after_in < before_in * 0.7, "the IBAN area is destroyed in the sent image, the rest is untouched"
    page.close()

    # "Show them" sends the image as it is.
    page = _open(browser_context, _stub(capture=_ocr_capture()))
    sent2: list = []
    _mock_vision(page, reply=OK_REPLY, record=sent2)
    page.get_by_test_id("companion-vision-open").click()
    page.get_by_test_id("vision-capture-screen").click()
    expect(page.get_by_test_id("vision-shield")).to_have_attribute("data-state", "hidden", timeout=10000)
    page.get_by_test_id("vision-shield-show").click()
    expect(page.get_by_test_id("vision-shield")).to_have_attribute("data-state", "shown")
    page.get_by_test_id("vision-send").click()
    expect(page.get_by_test_id("companion-msg-assistant").last).to_contain_text("colour gradient", timeout=10000)
    assert sent2[0]["image_base64"] == _png_b64(), "nothing was changed when the user chose to send it as it is"
    page.close()


def test_without_local_ocr_the_user_is_told_nothing_was_hidden(browser_context, workspace_ready):
    page = _open(browser_context, _stub())
    _mock_vision(page, reply=OK_REPLY, record=[])
    page.get_by_test_id("companion-vision-open").click()
    page.get_by_test_id("vision-capture-screen").click()
    expect(page.get_by_test_id("vision-shield")).to_have_attribute("data-state", "unavailable", timeout=10000)
    expect(page.get_by_test_id("vision-shield")).to_contain_text("not available")
    page.close()


def _summon(page, phase):
    page.evaluate("(p) => window.dispatchEvent(new CustomEvent('aether-companion-summon', {detail: {phase: p}}))", phase)


def _summoned_page(browser_context, vision_supported=True):
    page = _open(browser_context, _stub())
    page.evaluate("(c) => { window.__summon = c; }", _ocr_capture())
    sent: list = []
    _mock_vision(page, supported=vision_supported, reply=OK_REPLY, record=sent)
    chats: list = []
    page.route("**/api/personal/chat", lambda r: (chats.append(json.loads(r.request.post_data or "{}")), r.fulfill(status=200, content_type="application/json", body=json.dumps(
        {"id": "m1", "session_id": "s1", "role": "assistant", "content": "ok, noted", "metadata": {}, "created_at": "2026-01-01T00:00:00Z"})))[1])
    return page, sent, chats


def test_hold_and_ask_sends_the_shielded_screen_with_the_spoken_question(browser_context, workspace_ready):
    # The native summon is simulated (the key events and the screen it read); OCR words are the helper's output shape,
    # the shield route and the image pixelation are the real ones.
    page, sent, chats = _summoned_page(browser_context)
    _summon(page, "press")
    sight = page.get_by_test_id("companion-sight")
    expect(sight).to_have_attribute("data-state", "hidden", timeout=10000)
    expect(sight).to_contain_text("1 sensitive area(s) hidden")
    page.get_by_test_id("companion-input").fill("What is on my screen?")  # what dictation would have typed while the key was held
    _summon(page, "release")
    expect(page.get_by_test_id("companion-msg-assistant").last).to_contain_text("colour gradient", timeout=10000)
    assert len(sent) == 1 and sent[0]["prompt"] == "What is on my screen?" and chats == []
    before_in, before_out = _read_pixel(page, _png_b64(), 0.5, 0.5), _read_pixel(page, _png_b64(), 0.1, 0.9)
    after_in, after_out = _read_pixel(page, sent[0]["image_base64"], 0.5, 0.5), _read_pixel(page, sent[0]["image_base64"], 0.1, 0.9)
    assert after_out == before_out and after_in < before_in * 0.7, "the IBAN was hidden in the image that left"
    expect(page.get_by_test_id("companion-sight")).to_have_count(0)  # one message only: the next one does not carry the old screen
    assert [c[0] for c in page.evaluate("window.__native_calls")].count("companion_take_context") == 1
    page.close()


def test_a_model_without_vision_gets_the_text_read_locally_not_an_image(browser_context, workspace_ready):
    page, sent, chats = _summoned_page(browser_context, vision_supported=False)
    _summon(page, "press")
    expect(page.get_by_test_id("companion-sight")).to_have_attribute("data-state", "hidden", timeout=10000)
    page.get_by_test_id("companion-input").fill("Summarise this")
    _summon(page, "release")
    expect(page.get_by_test_id("companion-msg-assistant").last).to_contain_text("ok, noted", timeout=10000)
    assert sent == [] and len(chats) == 1
    assert chats[0]["prompt"].startswith("Summarise this") and "[Text read from the screen]" in chats[0]["prompt"] and "Fattura" in chats[0]["prompt"]
    expect(page.get_by_test_id("companion-msg-user").last).to_have_text("Summarise this")  # the dump is not shown as the user's message
    page.close()


def test_tap_cancel_and_dont_look_never_send_the_screen(browser_context, workspace_ready):
    page, sent, chats = _summoned_page(browser_context)
    _summon(page, "press")
    expect(page.get_by_test_id("companion-sight")).to_be_visible(timeout=10000)
    page.get_by_test_id("companion-sight-drop").click()
    expect(page.get_by_test_id("companion-sight")).to_have_count(0)
    page.get_by_test_id("companion-input").fill("hello")
    page.get_by_test_id("companion-send").click()
    expect(page.get_by_test_id("companion-msg-assistant").last).to_contain_text("ok, noted", timeout=10000)
    assert sent == [] and "[Text read from the screen]" not in chats[0]["prompt"]
    page.evaluate("(c) => { window.__summon = c; }", _ocr_capture())
    _summon(page, "press")
    expect(page.get_by_test_id("companion-sight")).to_be_visible(timeout=10000)
    _summon(page, "cancel")
    expect(page.get_by_test_id("companion-sight")).to_have_count(0)
    page.close()
