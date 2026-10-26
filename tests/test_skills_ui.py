"""Skills screen: permission badges and readiness come from the backend; a skill that needs a connection says so and leads to Connections."""
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
        context.add_init_script("localStorage.setItem('aether_home_view', 'transcript'); localStorage.setItem('aether_show_advanced', '1'); localStorage.setItem('aether_language', 'en');")
        if _state["token"]:
            context.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{_state['token']}';")
        yield context
        browser.close()


def _skill(name, perms, requires=None):
    return {"name": name, "description": name, "instructions": "x", "version": "1.0.0", "builtin": True, "category": "integration" if requires else "native",
            "permissions": [p["id"] for p in perms], "permission_details": perms, "requires": requires}


def test_badges_readiness_and_the_path_to_connections(browser_context):
    import test_personal_agent_ui as base

    base._state.update(_state)
    page = browser_context.new_page()
    _ensure_workspace(page)
    skills = [
        _skill("filesystem_tools", [{"id": "files.read", "risk": "read"}, {"id": "files.write", "risk": "write"}]),
        _skill("terminal_sandbox", [{"id": "shell.run", "risk": "sensitive"}]),
        _skill("github_tools", [{"id": "github.read", "risk": "read"}, {"id": "github.write", "risk": "sensitive"}], {"connection": "github", "state": "not_connected"}),
        _skill("gmail_integration", [{"id": "mail.read", "risk": "read"}], {"connection": "gmail", "state": "unavailable"}),
        _skill("slack_notifications", [{"id": "slack.send", "risk": "sensitive"}], {"connection": "slack", "state": "ready"}),
    ]
    assigns: list = []
    page.route("**/api/skills", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(skills)))
    page.route("**/api/skills/*/assign", lambda r: (assigns.append(r.request.url), r.fulfill(status=200, content_type="application/json", body='{"status":"success"}'))[1])
    if not page.locator("[data-testid='nav-workforce']").count():
        page.locator("[data-testid='nav-advanced']").click()
    page.locator("[data-testid='nav-workforce']").click()
    page.get_by_role("button", name="Skills").first.click()
    expect(page.get_by_test_id("perm-filesystem_tools-files.write")).to_have_text("Writes files", timeout=10000)
    expect(page.get_by_test_id("perm-terminal_sandbox-shell.run")).to_have_attribute("data-risk", "sensitive")
    expect(page.get_by_test_id("perm-github_tools-github.write")).to_have_text("Changes GitHub")
    assert page.get_by_text("net:http").count() == 0 and page.get_by_text("fs:write").count() == 0, "the old invented badges are gone"
    github = page.locator("div.card", has=page.get_by_test_id("perm-github_tools-github.read"))
    expect(github.get_by_role("button", name="Connect first")).to_be_visible()
    expect(page.locator("div.card", has=page.get_by_test_id("perm-gmail_integration-mail.read")).get_by_role("button", name="Coming soon")).to_be_visible()
    github.get_by_role("button", name="Connect first").click()
    expect(page.get_by_test_id("connections-view")).to_be_visible(timeout=10000)
    assert assigns == [], "nothing was assigned: the skill cannot work without its connection"
    page.close()
