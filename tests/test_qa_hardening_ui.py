"""
Browser flows for the QA pass (real server, real UI, no model needed): a rejected proposal stays rejected on the
server, and an ambiguous request is clarified from the chat card and resumes as a new proposal.
"""
from __future__ import annotations

import json
import urllib.request

import pytest
from playwright.sync_api import expect, sync_playwright

from test_personal_agent_ui import _ensure_workspace
from ui_isolation import clear_pending_work

_state: dict = {}


@pytest.fixture(scope="module")
def browser_context(aether_server):
    _state["base_url"] = aether_server["base_url"]
    _state["token"] = aether_server.get("token")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        context.add_init_script("localStorage.setItem('aether_experience_mode', 'v1');")
        if _state["token"]:
            context.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{_state['token']}';")
        yield context
        browser.close()


def _proposals():
    req = urllib.request.Request(_state["base_url"] + "/api/personal/proposals?limit=50")
    if _state["token"]:
        req.add_header("Authorization", f"Bearer {_state['token']}")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _send(page, text):
    box = page.locator("textarea[placeholder*='What would you like Aether to take care of']")
    box.fill(text)
    page.locator("button:has-text('Take Care of It')").click()


def test_rejecting_a_proposal_is_stored_by_the_server(browser_context):
    import test_personal_agent_ui as base
    base._state.update(_state)
    page = browser_context.new_page()
    _ensure_workspace(page); clear_pending_work(_state['base_url'], _state['token'])
    _send(page, "Create a document named qa_reject_check.md with key milestones")
    page.wait_for_selector("text=Confirmation Required", timeout=15000)
    page.locator("button:has-text('Reject')").first.click()
    expect(page.locator("text=Proposal declined").first).to_be_visible(timeout=8000)
    mine = [p for p in _proposals() if "qa_reject_check" in (p.get("objective") or "")]
    assert mine and all(p["status"] == "revoked" for p in mine), [p["status"] for p in mine]
    page.close()


def test_a_clarification_is_answered_in_the_card_and_the_request_resumes(browser_context):
    import test_personal_agent_ui as base
    base._state.update(_state)
    page = browser_context.new_page()
    _ensure_workspace(page); clear_pending_work(_state['base_url'], _state['token'])
    page.reload(); page.wait_for_selector('.sidebar')
    _send(page, "Leggi e aggiorna il file qa_missing_report_zz.md con i dati di vendita")
    card = page.locator("[data-testid='proposal-clarification']").first
    expect(card).to_be_visible(timeout=15000)
    expect(page.locator("button:has-text('Approve')")).to_have_count(0)      # a question is open: nothing to approve yet
    card.locator("input").fill("Il file non esiste ancora, crealo da zero")
    card.locator("button:has-text('Send answer')").click()
    expect(page.locator("text=Chiarimento dell'utente").first).to_be_visible(timeout=10000)
    page.wait_for_selector("button:has-text('Approve')", timeout=10000)
    mine = [p for p in _proposals() if "qa_missing_report_zz" in (p.get("objective") or "")]
    assert any(p["status"] == "superseded" for p in mine), [p["status"] for p in mine]
    page.close()
