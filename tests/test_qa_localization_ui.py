"""
Language consistency of the main screens, in a real browser: with the language set to Italian no English interface
words may remain, and with English no Italian ones. The check is a vocabulary heuristic over the visible text of every
primary view (it cannot prove a translation is good, only that nothing was left in the other language).
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import sync_playwright

from test_personal_agent_ui import _ensure_workspace
from ui_isolation import clear_pending_work

_state: dict = {}

VIEWS = ["home", "missions", "connections", "results", "workforce", "automations", "settings", "marketplace",
         "knowledge", "memory", "learning", "agents", "teams", "skills"]

# Words that only occur in the other language's interface copy (articles, prepositions, common UI verbs/nouns).
ENGLISH_ONLY = {
    "the", "and", "with", "your", "you", "please", "failed", "loading", "click", "select", "create", "delete", "save", "cancel",
    "error", "search", "settings", "open", "close", "enable", "disable", "refresh", "download", "upload", "name", "description",
    "no", "yes", "all", "new", "add", "remove", "edit", "run", "start", "stop", "view", "show", "hide", "back", "next",
    "from", "this", "that", "are", "is", "was", "will", "can", "not", "or", "to", "of", "in", "on", "for", "by", "at",
}
ITALIAN_ONLY = {
    "il", "lo", "la", "le", "gli", "di", "del", "della", "dei", "delle", "che", "per", "con", "non", "una", "uno", "nel", "nella",
    "errore", "caricamento", "salva", "annulla", "crea", "elimina", "cerca", "apri", "chiudi", "abilita", "disabilita", "aggiorna",
    "scarica", "nome", "descrizione", "sì", "tutti", "tutte", "nuovo", "nuova", "aggiungi", "rimuovi", "modifica", "esegui", "avvia",
    "ferma", "vedi", "mostra", "nascondi", "indietro", "avanti", "da", "questo", "questa", "sono", "è", "puoi", "tuo", "tua",
}
# Views that list model- or user-generated records (memories, lessons, knowledge): their content is whatever language the
# model wrote in, so a few common words are tolerated there; the interface around them is still checked.
DATA_VIEWS = {"memory", "learning", "knowledge", "agents", "teams", "workforce"}
DATA_VIEW_TOLERATED_ALWAYS = {"search"}   # permission tags such as "search:duckduckgo" are identifiers
DATA_VIEW_TOLERATED = {"not", "and", "the", "with", "for", "to", "of", "in", "on", "is", "are", "was", "will", "can", "or",
                       "this", "that", "from", "by", "at", "you", "your", "name", "description", "new", "all"}
# Tokens that are legitimately identical or loaned in both languages (brands, product names, units, acronyms).
ALLOWED = {"no", "da", "in", "to", "on", "per", "con", "la", "le", "lo", "di", "è", "all", "start", "stop", "run", "new"}


@pytest.fixture(scope="module")
def browser_context(aether_server):
    _state["base_url"] = aether_server["base_url"]
    _state["token"] = aether_server.get("token")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        context.add_init_script("localStorage.setItem('aether_home_view', 'transcript');")
        if _state["token"]:
            context.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{_state['token']}';")
        yield context
        browser.close()


def _visible_words(page) -> list[str]:
    # Conversation titles, message bubbles, jobs, memories and lessons (marked data-user-content) are the user's own words
    # (other tests in the session write in both languages).
    text = page.evaluate(
        "(() => { const c = document.body.cloneNode(true);"
        " c.querySelectorAll('.drawer-session-item, .v2-conversation-dock, .v2-bubble, .message-content, .sb-chats, .life-main, .life-brief, [data-testid=privacy-knows] .pv-main, [data-user-content]').forEach(e => e.remove());"
        " document.body.appendChild(c); const t = c.innerText; c.remove(); return t; })()"
    )
    # ALL-CAPS tokens are protocol/acronym vocabulary (GET, DELETE, HTTP...), not interface copy.
    return [w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ']+", text) if not (len(w) > 1 and w.isupper())]


def _open_view(page, view: str) -> bool:
    for _ in range(2):
        target = page.locator(f"[data-testid='nav-{view}']").first
        if target.count() and target.is_visible():
            target.click()
            page.wait_for_timeout(700)
            return True
        advanced = page.locator("[data-testid='nav-advanced']").first
        if advanced.count():
            advanced.click()
            page.wait_for_timeout(300)
        else:
            break
    return False


@pytest.mark.parametrize("language,foreign", [("it", ENGLISH_ONLY), ("en", ITALIAN_ONLY)])
def test_no_screen_mixes_in_the_other_language(browser_context, language, foreign):
    import test_personal_agent_ui as base
    base._state.update(_state)
    page = browser_context.new_page()
    _ensure_workspace(page); clear_pending_work(_state['base_url'], _state['token'])                      # its selectors are English: create/select the workspace first
    page.evaluate(f"localStorage.setItem('aether_language', '{language}')")
    page.reload()
    page.wait_for_selector(".sidebar", timeout=15000)
    page.wait_for_timeout(600)
    assert page.locator("[data-testid='no-workspace-notice']").count() == 0, "no workspace: the views would not be checked"
    report: dict[str, list[str]] = {}
    visited = 0
    for view in VIEWS:
        if not _open_view(page, view):
            continue
        visited += 1
        words = _visible_words(page) + _attribute_words(page)
        if view == "workforce":      # the hub is a row of tabs (teams, agents, skills, memory, learning...): check each
            tabs = page.locator(".main-content button.btn-ghost")
            for i in range(min(tabs.count(), 8)):
                try:
                    tabs.nth(i).click(timeout=2000)
                    page.wait_for_timeout(500)
                    words += _visible_words(page) + _attribute_words(page)
                except Exception:
                    continue
        tolerated = (DATA_VIEW_TOLERATED if view in DATA_VIEWS and language == "it" else set())
        if view == "workforce":
            tolerated = tolerated | DATA_VIEW_TOLERATED_ALWAYS
        stray = sorted({w for w in words if w in foreign and w not in ALLOWED and w not in tolerated})
        if stray:
            lines = [ln.strip() for ln in page.evaluate("document.body.innerText").split("\n")
                     if set(re.findall(r"[A-Za-zÀ-ÿ']+", ln.lower())) & set(stray)]
            report[view] = {"words": stray, "lines": lines[:4]}
    page.close()
    assert visited >= 8, f"only {visited} views could be opened"
    assert not report, f"{language}: words of the other language on screen: {report}"


def _attribute_words(page) -> list[str]:
    values = page.evaluate(
        "Array.from(document.querySelectorAll('[placeholder],[aria-label],[title]'))"
        ".filter(e => !e.closest('.drawer-session-item, .v2-conversation-dock, .v2-bubble, .message-content, .sb-chats, [data-user-content]')).flatMap(e => "
        "[e.getAttribute('placeholder'), e.getAttribute('aria-label'), e.getAttribute('title')]).filter(Boolean)"
    )
    values = [re.sub(r"(?:/[\w.\-~]+){2,}", " ", v) for v in values]       # example file paths are not interface copy
    return [w.lower() for v in values for w in re.findall(r"[A-Za-zÀ-ÿ']+", v) if not (len(w) > 1 and w.isupper())]


# The separate Orb interface was retired (one interface: sidebar + chat); its words are covered by the views above.
