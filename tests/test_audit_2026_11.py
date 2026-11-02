"""What the November audit found with the real model, fixed: questions whose answer is on the web are searched (Groq's own
browser_search, DuckDuckGo as fallback) and answered with sources; "cosa ho domani?" includes Aether's own reminders and says
when Google Calendar is not connected; a mail without Gmail is written in full, signed with the user's name, and says it was not
sent; a remembered fact is said back in the second person; "ti ricordo di chiamare"; "Ricordare il contratto" becomes a title
that reads on its own; Settings → "Sincronizza tutto" calls a route that exists."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

from aether.life.store import life_store_for
from aether.personal import tool_router
from aether.personal.service import _as_said_to_you, _note_sentence
from aether.tools.web_search import DuckDuckGoSearchBackend, WebSearchResult
from aether.workspace.workspace import Workspace


class Scripted:
    """A fake model: the router gets `route`, the mail writer gets `mail`, anything else gets `text`."""

    def __init__(self, route=None, mail=None, text="ok"):
        self.route, self.mail, self.text, self.calls = route or {"action": "none"}, mail, text, []

    def generate(self, messages, tools=None, output_schema=None):
        system = messages[0].content if messages else ""
        self.calls.append({"system": system, "tools": tools})
        if system.startswith("You map ONE user message"):
            return SimpleNamespace(content=json.dumps(self.route))
        if system.startswith("You write ONE email"):
            return SimpleNamespace(content=json.dumps(self.mail))
        return SimpleNamespace(content=self.text)


class Down:
    def generate(self, *a, **k):
        raise TimeoutError("model unreachable")


# -- web search -------------------------------------------------------------------------------------------------------------
def test_search_online_is_understood_even_with_the_model_down():
    r = tool_router.route("cerca su internet chi ha vinto l'ultimo gran premio di formula 1", provider=Down())
    assert r == {"action": "web_search", "query": "chi ha vinto l'ultimo gran premio di formula 1"}
    assert tool_router.route("search online for the best pizza in Turin", provider=Down())["query"] == "the best pizza in Turin"
    assert tool_router.route("cerca il file del contratto", provider=Down())["action"] == "none"


def test_web_shaped_questions_reach_the_router_and_small_talk_does_not():
    assert tool_router.worth_routing("a che ora apre il museo egizio?")
    assert tool_router.worth_routing("chi ha vinto ieri la partita della Juve?")
    assert tool_router.worth_routing("what's the latest news about Apple?")
    assert not tool_router.worth_routing("oggi sono stanco")
    assert not tool_router.worth_routing("ciao, come va?")


def test_the_router_turns_a_web_question_into_a_search():
    r = tool_router.route("chi ha vinto ieri la partita della Juve?", provider=Scripted(route={"action": "web_search", "web_query": "Juventus risultato 1 novembre 2026"}))
    assert r == {"action": "web_search", "query": "Juventus risultato 1 novembre 2026"}


class GroqLike(Scripted):
    PROVIDER_ID = "groq"
    config = SimpleNamespace(model="openai/gpt-oss-120b")

    def generate(self, messages, tools=None, output_schema=None):
        if tools:
            self.calls.append({"tools": tools})
            return SimpleNamespace(content="La Juventus ha battuto il Napoli 2-0.",
                                   sources=[{"title": "Serie A: Juventus-Napoli 2-0", "url": "https://www.ansa.it/juve-napoli"}])
        return super().generate(messages, tools, output_schema)


def test_with_groq_the_model_searches_on_groqs_side_and_the_answer_carries_the_sources(tmp_path):
    ws = Workspace.init(tmp_path, name="web-groq")
    try:
        svc = ws.personal
        model = GroqLike(route={"action": "web_search", "web_query": "Juventus risultato ieri"})
        svc._router_provider_override = model
        msg = svc.process_prompt(workspace_id=ws.name, prompt="chi ha vinto ieri la partita della Juve?")
        assert "Napoli 2-0" in msg.content
        assert "Fonti:\n- [Serie A: Juventus-Napoli 2-0](https://www.ansa.it/juve-napoli)" in msg.content
        assert any(c.get("tools") == [{"type": "browser_search"}] for c in model.calls)
    finally:
        ws.close()


def test_without_groq_duckduckgo_results_are_summarised_and_only_the_cited_ones_listed(tmp_path, monkeypatch):
    results = [WebSearchResult("Annuncio", "https://duckduckgo.com/y.js?ad_domain=x", "sponsored"),
               WebSearchResult("Orari - Museo Egizio", "https://museoegizio.it/info/orari/", "Aperto dalle 9 alle 18:30"),
               WebSearchResult("Altro", "https://example.com/altro", "niente")]
    monkeypatch.setattr(DuckDuckGoSearchBackend, "search", lambda self, q, max_results=5, timeout=10.0: results)
    ws = Workspace.init(tmp_path, name="web-ddg")
    try:
        svc = ws.personal
        svc._router_provider_override = Scripted(route={"action": "web_search", "web_query": "orari museo egizio"}, text="Apre alle 9 【1】.")
        msg = svc.process_prompt(workspace_id=ws.name, prompt="a che ora apre il museo egizio di torino?")
        assert msg.content.startswith("Apre alle 9 [1].")
        assert "museoegizio.it/info/orari" in msg.content
        assert "y.js" not in msg.content and "example.com" not in msg.content, "ads dropped, uncited results not listed"
    finally:
        ws.close()


def test_no_results_is_said_plainly(tmp_path, monkeypatch):
    monkeypatch.setattr(DuckDuckGoSearchBackend, "search", lambda self, q, max_results=5, timeout=10.0: [])
    ws = Workspace.init(tmp_path, name="web-none")
    try:
        svc = ws.personal
        svc._router_provider_override = Scripted(route={"action": "web_search", "web_query": "x"})
        msg = svc.process_prompt(workspace_id=ws.name, prompt="cerca su internet le ultime notizie su Marte")
        assert "non riesco a cercare in rete" in msg.content
    finally:
        ws.close()


def test_duckduckgo_snippets_are_parsed():
    page = """
    <div class="result results_links results_links_deep web-result ">
      <div class="links_main links_deep result__body">
        <h2 class="result__title"><a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&amp;rut=1">Primo</a></h2>
        <div class="result__extras"><div class="result__extras__url"></div></div>
      </div>
      <a class="result__snippet" href="https://example.com/a">Il <b>primo</b> estratto</a>
      <div class="clear"></div>
    </div>
    </div>
    <div class="result results_links results_links_deep web-result ">
      <h2 class="result__title"><a class="result__a" href="https://example.com/b">Secondo</a></h2>
      <a class="result__snippet" href="https://example.com/b">Secondo estratto</a>
    </div>"""
    r = DuckDuckGoSearchBackend()._parse_html(page, max_results=5)
    assert [(x.title, x.url, x.snippet) for x in r] == [("Primo", "https://example.com/a", "Il primo estratto"),
                                                        ("Secondo", "https://example.com/b", "Secondo estratto")]


def test_groq_browser_search_is_forced_and_its_sources_kept(monkeypatch):
    from aether.core.execution import Message
    from aether.providers.groq_provider import GroqProvider
    from aether.providers.types import ProviderConfig

    p = GroqProvider(ProviderConfig(model="openai/gpt-oss-120b", api_key="test"))
    body = p._build_body([Message(role="user", content="x")], [{"type": "browser_search"}], None, stream=False)
    assert body["tools"] == [{"type": "browser_search"}] and body["tool_choice"] == "required"
    data = {"model": "openai/gpt-oss-120b", "choices": [{"message": {
        "content": "Juventus-Napoli 2-0【1†L5-L13】.",
        "executed_tools": [
            {"type": "search", "search_results": {"results": [{"title": "Gazzetta", "url": "https://gazzetta.it/x"}, {"title": "Ansa", "url": "https://ansa.it/y"}]}},
            {"type": "open", "search_results": {"results": [{"title": "www.ansa.it - viewing lines [0 - 29] of 29", "url": "https://ansa.it/y"}]}},
        ]}}]}
    monkeypatch.setattr(p, "_post_json", lambda path, b: data)
    r = p.generate([Message(role="user", content="chi ha vinto?")], tools=[{"type": "browser_search"}])
    assert r.content == "Juventus-Napoli 2-0."
    assert [s["url"] for s in r.sources] == ["https://ansa.it/y", "https://gazzetta.it/x"], "the page it read comes first"


# -- calendar answers -------------------------------------------------------------------------------------------------------
def test_what_is_on_tomorrow_includes_aethers_own_reminders_and_says_the_calendar_is_not_connected(tmp_path):
    ws = Workspace.init(tmp_path, name="cal-own")
    try:
        store = life_store_for(ws)
        tomorrow_10 = (dt.datetime.now().astimezone() + dt.timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        store.add_reminder("chiamare il dentista", due_at=tomorrow_10.timestamp())
        svc = ws.personal
        svc._router_provider_override = Scripted()
        msg = svc.process_prompt(workspace_id=ws.name, prompt="cosa ho in calendario domani?")
        assert "- 10:00 Chiamare il dentista" in msg.content, msg.content
        assert "Non risultano" not in msg.content
        assert "Google Calendar non è collegato" in msg.content
    finally:
        ws.close()


# -- mail without Gmail -----------------------------------------------------------------------------------------------------
def test_a_mail_without_gmail_is_signed_with_the_users_name_and_says_it_was_not_sent(tmp_path):
    ws = Workspace.init(tmp_path, name="mail-signed")
    try:
        life_store_for(ws).update_settings(user_name="Matteo")
        svc = ws.personal
        model = Scripted(route={"action": "mail_compose", "contact_name": "Mario", "instructions": "ricordargli i 200 euro"},
                         mail={"subject": "Promemoria pagamento", "body": "Ciao Mario,\n\nti ricordo i 200 euro.\n\nA presto,\nMatteo"})
        svc._router_provider_override = model
        msg = svc.process_prompt(workspace_id=ws.name, prompt="scrivi una mail a Mario per ricordargli i 200 euro")
        assert msg.content.startswith("**Oggetto:** Promemoria pagamento")
        assert "Gmail non è collegato, quindi non l'ho inviata né salvata" in msg.content
        writer = next(c["system"] for c in model.calls if c["system"].startswith("You write ONE email"))
        assert 'signed "Matteo"' in writer
    finally:
        ws.close()


# -- wording ----------------------------------------------------------------------------------------------------------------
def test_a_remembered_fact_is_said_back_to_the_user():
    assert _as_said_to_you("il mio colore preferito è il blu", False) == "il tuo colore preferito è il blu"
    assert _as_said_to_you("mi chiamo Matteo e ho 19 anni", False) == "ti chiami Matteo e hai 19 anni"
    assert _as_said_to_you("odio il caffè", False) == "odi il caffè"
    assert _as_said_to_you("Mario è mio cugino", False) == "Mario è tuo cugino"
    assert _as_said_to_you("I am allergic to nuts and my dog is Rex", True) == "you are allergic to nuts and your dog is Rex"


def test_remember_reply_in_chat(tmp_path):
    ws = Workspace.init(tmp_path, name="remember")
    try:
        msg = ws.personal.process_prompt(workspace_id=ws.name, prompt="ricordati che il mio colore preferito è il blu")
        assert msg.content == "Fatto, me lo ricordo: il tuo colore preferito è il blu"
    finally:
        ws.close()


def test_an_infinitive_reminder_takes_di():
    assert _note_sentence({"kind": "reminder", "title": "Chiamare il dentista"}, False) == "Ti ricordo di **chiamare il dentista**"
    assert _note_sentence({"kind": "reminder", "title": "Dirgli del contratto"}, True) == "Ti ricorderò di **dirgli del contratto**"
    assert _note_sentence({"kind": "reminder", "title": "Compleanno di Anna"}, False) == "Ti ricordo **Compleanno di Anna**"


def test_a_meta_reminder_title_becomes_the_topic():
    p = "quando sento giulia ricordami del contratto"
    assert tool_router._complete_title("Ricordare il contratto", p, "Giulia") == "Parlare con Giulia del contratto"
    assert tool_router._complete_title("Ricordare l'anticipo", p, "Giulia") == "Parlare con Giulia dell'anticipo"
    assert tool_router._complete_title("Chiederle del contratto", p, "Giulia") == "Chiederle del contratto"


# -- UI calls that must exist -----------------------------------------------------------------------------------------------
def test_sync_all_calls_the_real_route():
    src = (Path(__file__).resolve().parent.parent / "ui" / "src" / "ConnectionsAdvanced.tsx").read_text(encoding="utf-8")
    assert "sync_all" not in src and "apiUrl('/api/connections/sync')" in src and "total_items_synced" in src
