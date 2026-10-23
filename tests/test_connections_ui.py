"""Connections screen: one row per service, one-click connect with a waiting state, cancel, readable errors, GitHub device code.
The OAuth endpoints are mocked (the real flow engine is covered by tests/test_oauth_flow.py); this checks what the person sees and the calls made."""
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
        context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
        context.add_init_script("localStorage.setItem('aether_experience_mode', 'v1'); localStorage.setItem('aether_language', 'en');")
        if _state["token"]:
            context.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{_state['token']}';")
        yield context
        browser.close()


def _open(context, providers, conns_box, flow_script):
    import test_personal_agent_ui as base

    base._state.update(_state)
    page = context.new_page()
    _ensure_workspace(page)  # the app first, the mocks after: they must not interfere with booting
    calls: dict[str, list] = {"flow": [], "device": [], "cancel": [], "open": [], "disconnect": []}
    page.route("**/api/connections/oauth/providers", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(providers)))
    page.route("**/api/connections", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(conns_box["list"])) if r.request.method == "GET" else r.fallback())
    page.route("**/api/connections/*/oauth/flow", lambda r: (calls["flow"].append(r.request.url), r.fulfill(status=200, content_type="application/json", body=json.dumps({"state": "st-1", "auth_url": "https://accounts.example/authorize?x=1", "redirect_uri": "http://127.0.0.1:5555/callback"})))[1])
    page.route("**/api/connections/github/oauth/device", lambda r: (calls["device"].append(1), r.fulfill(status=200, content_type="application/json", body=json.dumps({"state": "dev-1", "user_code": "ABCD-1234", "verification_uri": "https://github.com/login/device", "expires_in": 600})))[1])
    page.route("**/api/system/open-browser", lambda r: (calls["open"].append(json.loads(r.request.post_data or "{}")), r.fulfill(status=200, content_type="application/json", body="{}"))[1])

    def status(route):
        if route.request.method == "DELETE":
            calls["cancel"].append(route.request.url)
            route.fulfill(status=200, content_type="application/json", body='{"cancelled":true}')
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(flow_script(route.request.url)))

    page.route("**/api/connections/oauth/flows/*", status)
    page.route("**/api/connections/*/disconnect", lambda r: (calls["disconnect"].append(r.request.url), conns_box.update(list=[]), r.fulfill(status=200, content_type="application/json", body="{}"))[1])
    if not page.locator("[data-testid='nav-connections']").count():  # it lives under the collapsed "More" group
        page.locator("[data-testid='nav-advanced']").click()
    page.locator("[data-testid='nav-connections']").click()
    expect(page.get_by_test_id("connections-view")).to_be_visible(timeout=10000)
    return page, calls


NONE_READY = {"google_calendar": {"ready_for_user_connect": False, "has_client_id": False}, "github": {"ready_for_user_connect": False, "has_client_id": False}}
GOOGLE_READY = {"google_calendar": {"ready_for_user_connect": True, "has_client_id": True}, "github": {"ready_for_user_connect": False, "has_client_id": True}}


def test_without_a_client_id_a_service_says_so_honestly_and_points_to_advanced(browser_context):
    page, _ = _open(browser_context, NONE_READY, {"list": []}, lambda u: {"status": "pending"})
    row = page.get_by_test_id("conn-row-google_calendar")
    expect(row).to_contain_text("for now with your own key, under Advanced")
    expect(page.get_by_test_id("conn-connect-google_calendar")).to_have_count(0)
    page.get_by_test_id("conn-setup-google_calendar").click()
    expect(page.get_by_test_id("connections-advanced")).to_be_visible()
    page.close()


def test_one_click_connect_waits_then_shows_the_account(browser_context):
    box = {"list": []}
    seen = {"n": 0}

    def script(url):
        seen["n"] += 1
        if seen["n"] < 3:
            return {"status": "pending"}
        box["list"] = [{"provider": "google_calendar", "status": "verified", "account_name": "matteo@example.com"}]
        return {"status": "success", "account": "matteo@example.com"}

    page, calls = _open(browser_context, GOOGLE_READY, box, script)
    page.get_by_test_id("conn-connect-google_calendar").click()
    row = page.get_by_test_id("conn-row-google_calendar")
    expect(row).to_have_attribute("data-state", "waiting")
    expect(row).to_contain_text("Waiting for your browser")
    expect(page.get_by_test_id("conn-cancel-google_calendar")).to_be_visible()
    expect(row).to_have_attribute("data-state", "connected", timeout=15000)
    expect(row).to_contain_text("Connected as matteo@example.com")
    assert calls["flow"] and calls["open"] and calls["open"][0]["url"].startswith("https://accounts.example/authorize"), "the system browser is asked to open the authorization URL"
    page.get_by_test_id("conn-disconnect-google_calendar").click()
    expect(row).to_have_attribute("data-state", "none", timeout=10000)
    page.close()


def test_cancel_and_denial_are_handled_with_plain_words(browser_context):
    page, calls = _open(browser_context, GOOGLE_READY, {"list": []}, lambda u: {"status": "pending"})
    page.get_by_test_id("conn-connect-google_calendar").click()
    page.get_by_test_id("conn-cancel-google_calendar").click()
    expect(page.get_by_test_id("conn-row-google_calendar")).to_have_attribute("data-state", "none")
    assert calls["cancel"], "cancelling closes the listener on the server"
    page.close()

    page, _ = _open(browser_context, GOOGLE_READY, {"list": []}, lambda u: {"status": "error", "error": "denied:access_denied"})
    page.get_by_test_id("conn-connect-google_calendar").click()
    expect(page.get_by_test_id("conn-error-google_calendar")).to_have_text("You cancelled the authorization.", timeout=10000)
    page.close()

    page, _ = _open(browser_context, GOOGLE_READY, {"list": []}, lambda u: {"status": "error", "error": "exchange_failed:invalid_grant"})
    page.get_by_test_id("conn-connect-google_calendar").click()
    expect(page.get_by_test_id("conn-error-google_calendar")).to_contain_text("The service refused the connection", timeout=10000)
    page.close()


def test_github_shows_the_device_code_instead_of_asking_for_keys(browser_context):
    page, calls = _open(browser_context, GOOGLE_READY, {"list": []}, lambda u: {"status": "pending"})
    page.get_by_test_id("conn-connect-github").click()
    expect(page.get_by_test_id("cn-device-code")).to_contain_text("ABCD-1234")
    expect(page.get_by_test_id("conn-row-github")).to_contain_text("github.com/login/device")
    assert calls["device"] and not calls["flow"], "GitHub uses the device flow: no redirect and no secret"
    page.close()


def test_telegram_is_set_up_with_a_token_and_paired_with_a_one_time_link(browser_context):
    import test_personal_agent_ui as base

    base._state.update(_state)
    page = browser_context.new_page()
    _ensure_workspace(page)
    status = {"configured": False}
    sent = []
    page.route("**/api/connections/telegram/mobile", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(status)))

    def setup(route):
        sent.append(json.loads(route.request.post_data or "{}"))
        if sent[-1].get("bot_token") == "bad":
            route.fulfill(status=400, content_type="application/json", body=json.dumps({"detail": {"code": "invalid_token"}}))
            return
        status.update({"configured": True, "bot_username": "aether_test_bot", "paired": []})
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"status": "ok", "bot_username": "aether_test_bot", "code": "abc", "link": "https://t.me/aether_test_bot?start=abc"}))

    page.route("**/api/connections/telegram/mobile/setup", setup)
    if not page.locator("[data-testid='nav-connections']").count():
        page.locator("[data-testid='nav-advanced']").click()
    page.locator("[data-testid='nav-connections']").click()
    row = page.get_by_test_id("conn-row-telegram")
    expect(row).to_contain_text("Write to Aether from your phone")
    row.get_by_test_id("tg-open").click()
    expect(row).to_contain_text("BotFather")
    row.get_by_test_id("tg-token-input").fill("bad")
    row.get_by_test_id("tg-setup-btn").click()
    expect(row.get_by_role("alert")).to_contain_text("did not accept")
    row.get_by_test_id("tg-token-input").fill("123456789:" + "A" * 35)
    row.get_by_test_id("tg-setup-btn").click()
    expect(row.get_by_test_id("tg-link")).to_have_text("https://t.me/aether_test_bot?start=abc")
    status["paired"] = [{"chat_id": "42", "name": "Matteo"}]
    expect(row).to_contain_text("Paired with Matteo", timeout=8000)
    assert row.get_attribute("data-state") == "connected"
    page.close()
