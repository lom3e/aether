"""New in November: Concentrazione (non-urgent notifications stay in the bell for a while, then one summary of what arrived),
the diary ("cosa ho fatto questa settimana / per Rossi?" answered from facts only) and web search with the user's own Brave or
Tavily key (no CAPTCHA, any model)."""
from __future__ import annotations

import datetime as dt
import json
import time
from types import SimpleNamespace

import asyncio

import pytest
from fastapi import HTTPException, Request

from aether.life import diary, focus
from aether.life.store import LifeStore, life_store_for
from aether.notifications.dispatcher import NotificationDispatcher
from aether.notifications.models import ChannelType, Notification, NotificationPriority
from aether.server import routes
from aether.server.app import app
from aether.tools import web_search
from aether.tools.web_search import BraveSearchBackend, TavilySearchBackend, WebSearchResult
from aether.workspace.workspace import Workspace


class Quiet:
    """A model that should not be asked: the new answers are facts only."""

    def __init__(self):
        self.calls = 0

    def generate(self, messages, tools=None, output_schema=None):
        self.calls += 1
        system = messages[0].content if messages else ""
        if system.startswith("You map ONE user message"):
            return SimpleNamespace(content=json.dumps({"action": "none"}))
        return SimpleNamespace(content="ok")


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path / "data"))
    w = Workspace.init(tmp_path / "ws", name="focus-diary")
    yield w
    w.close()
    focus._active.clear()
    focus._held.clear()


# -- Concentrazione -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("said,expected", [
    ("voglio concentrarmi per 45 minuti", ("start", 45)),
    ("non disturbarmi per un'ora", ("start", 60)),
    ("modalità concentrazione", ("start", focus.DEFAULT_MINUTES)),
    ("let me focus for 2 hours", ("start", 120)),
    ("fammi concentrare mezz'ora", ("start", 30)),
    ("fine concentrazione", ("stop", 0)),
    ("concentrati sul preventivo", None),  # an instruction to Aether, not a focus window
    ("che tempo fa domani?", None),
])
def test_focus_is_understood_from_plain_sentences(said, expected):
    assert focus.parse(said) == expected


def test_focus_survives_a_restart_and_ends_with_what_was_kept_quiet(tmp_path):
    store = LifeStore(tmp_path / "life.db")
    st = focus.start(store, "w1", 30)
    assert st["active"] and 29 * 60 <= st["remaining_s"] <= 30 * 60 and focus.is_active("w1")
    focus._active.clear()  # a restart: the window is read back from the settings
    assert focus.status(store, "w1")["active"] and focus.is_active("w1")
    focus.hold("w1", "Pronto per la riunione con Rossi")
    started, held = focus.stop(store, "w1")
    assert started and held == ["Pronto per la riunione con Rossi"] and not focus.is_active("w1")
    text = focus.summary(SimpleNamespace(id="w1"), store, started, held)
    assert text.startswith("Fine della concentrazione") and "«Pronto per la riunione con Rossi»" in text


def test_a_short_window_and_nothing_new_say_so(tmp_path):
    store = LifeStore(tmp_path / "life.db")
    assert focus.start(store, "w2", 1)["minutes"] == 5  # at least five minutes
    started, held = focus.stop(store, "w2")
    assert focus.summary(SimpleNamespace(id="w2"), store, started, held).endswith("Nel frattempo non è arrivato niente.")
    assert "Nothing arrived meanwhile." in focus.summary(SimpleNamespace(id="w2"), store, started, held, language="en")
    long_ago = time.time() - 5 * 3600  # ran out while Aether was closed: it lasted 50 minutes, not five hours
    assert "(50 minuti)" in focus.summary(SimpleNamespace(id="w2"), store, long_ago, [], until=long_ago + 50 * 60)


def test_during_focus_non_urgent_notifications_stay_in_the_bell_and_urgent_ones_pass(ws):
    disp = NotificationDispatcher.__new__(NotificationDispatcher)  # only the routing decision is under test
    normal = Notification(id="n1", workspace_id="wsx", type="insight", title="Pronto per la riunione", message="", priority=NotificationPriority.NORMAL)
    urgent = Notification(id="n2", workspace_id="wsx", type="insight", title="Approvazione", message="", priority=NotificationPriority.HIGH)
    focus._active["wsx"] = (time.time() - 10, time.time() + 600)
    assert disp._evaluate_rules(normal, []) == {ChannelType.IN_APP}
    assert focus._held["wsx"] == ["Pronto per la riunione"]
    assert disp._evaluate_rules(urgent, []) != {ChannelType.IN_APP}  # urgent gets through as usual
    focus._active.pop("wsx")
    assert ChannelType.DESKTOP in disp._evaluate_rules(normal, [])


def test_focus_by_voice_starts_and_ends_and_the_app_is_told(ws):
    svc = ws.personal
    model = Quiet()
    svc._router_provider_override = model
    msg = svc.process_prompt(workspace_id=ws.name, prompt="voglio concentrarmi per 40 minuti")
    assert msg.content.startswith("Concentrazione fino alle") and msg.metadata.get("focus") == "start"
    assert focus.is_active(ws.id)
    end = svc.process_prompt(workspace_id=ws.name, prompt="fine concentrazione", session_id=msg.session_id)
    assert end.content.startswith("Fine della concentrazione") and end.metadata.get("focus") == "stop"
    assert not focus.is_active(ws.id)
    again = svc.process_prompt(workspace_id=ws.name, prompt="fine concentrazione", session_id=msg.session_id)
    assert again.content == "La concentrazione non è attiva."


def _req(method="GET", path="/api/focus") -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": [], "app": app})


def test_focus_and_diary_routes(ws):
    app.state.workspace = ws
    assert asyncio.run(routes.focus_status_route(_req()))["active"] is False
    assert asyncio.run(routes.focus_stop_route(_req("DELETE")))["text"] == ""  # nothing to end
    on = asyncio.run(routes.focus_start_route(_req("POST"), routes.FocusPayload(minutes=25)))
    assert on["active"] and on["minutes"] == 25
    off = asyncio.run(routes.focus_stop_route(_req("DELETE"), language="en"))
    assert off["text"].startswith("Focus over") and off["active"] is False
    life_store_for(ws).update_job(life_store_for(ws).add_job("Fattura ottobre")["id"], status="done")
    d = asyncio.run(routes.diary_route(_req(path="/api/diary"), q="cosa ho fatto oggi"))
    assert d["count"] == 1 and "Fattura ottobre" in d["text"]


def test_web_search_key_is_tested_before_it_is_saved(ws, monkeypatch):
    app.state.workspace = ws
    import urllib.error

    def refuse(self, q, max_results=5, timeout=10.0):
        raise urllib.error.HTTPError("https://api.search.brave.com", 401, "no", {}, None)

    monkeypatch.setattr(BraveSearchBackend, "search", refuse)
    with pytest.raises(HTTPException) as e:
        asyncio.run(routes.web_search_save_route(_req("PUT", "/api/web-search"), routes.WebSearchPayload(provider="brave", api_key="bad")))
    assert e.value.status_code == 400 and e.value.detail["code"] == "invalid_key"
    assert asyncio.run(routes.web_search_settings_route(_req(path="/api/web-search")))["configured"] is False
    monkeypatch.setattr(BraveSearchBackend, "search", lambda self, q, max_results=5, timeout=10.0: [WebSearchResult("a", "https://a", "")])
    ok = asyncio.run(routes.web_search_save_route(_req("PUT", "/api/web-search"), routes.WebSearchPayload(provider="brave", api_key="good")))
    assert ok == {"provider": "brave", "configured": True, "results": 1}
    got = asyncio.run(routes.web_search_settings_route(_req(path="/api/web-search")))
    assert got["provider"] == "brave" and "good" not in json.dumps(got)  # the key never comes back
    asyncio.run(routes.web_search_delete_route(_req("DELETE", "/api/web-search")))
    assert web_search.keyed_backend(ws) is None


# -- diary --------------------------------------------------------------------------------------------------------------
def _store_with_a_week(tmp_path) -> tuple[LifeStore, dict]:
    store = LifeStore(tmp_path / "life.db")
    rossi = store.add_contact("Mario Rossi", kind="client")
    job = store.add_job("Preventivo sito", contact_id=rossi["id"])
    store.update_job(job["id"], status="done")
    store.update_job(store.add_job("Logo nuovo")["id"], status="done")
    r = store.add_reminder("chiamare il dentista")
    store.complete_reminder(r["id"])
    store.add_reminder("comprare il latte")  # not done: not in the diary
    m = store.add_money(rossi["id"], "owed_to_me", 200, what="consulenza")
    store.set_money_status(m["id"], "paid")
    return store, rossi


def test_the_diary_lists_what_was_done_this_week_day_by_day(tmp_path):
    store, _ = _store_with_a_week(tmp_path)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    timeline = [{"action_id": "gmail.send", "title": "Preventivo Rossi", "created_at": now_iso},
                {"action_id": "calendar.create_event", "title": "Call", "created_at": now_iso, "undone": True},  # taken back
                {"action_id": "life.add_job", "title": "x", "created_at": now_iso}]  # bookkeeping, already a job
    out = diary.build(store, "cosa ho fatto questa settimana?", timeline=timeline)
    t = out["text"]
    assert out["count"] == 5 and t.startswith("Cosa hai fatto questa settimana: **5** cose in 1 giorno.")
    for line in ("- ✓ Preventivo sito (per Mario Rossi)", "- ✓ Logo nuovo", "- ✓ Chiamare il dentista",
                 "- € Incassati da Mario Rossi: 200 € (consulenza)", "- Mail inviata: Preventivo Rossi"):
        assert line in t
    assert "latte" not in t and "Call" not in t


def test_the_diary_for_one_client_reads_as_a_report(tmp_path):
    store, rossi = _store_with_a_week(tmp_path)
    out = diary.build(store, "cosa ho fatto per Rossi questa settimana?",
                      timeline=[{"action_id": "gmail.send", "title": "Preventivo Rossi", "created_at": time.time()}])
    t = out["text"]
    assert t.startswith("Cosa hai fatto per **Mario Rossi** questa settimana: **3** cose")
    assert "Logo nuovo" not in t and "dentista" not in t and "Mail inviata: Preventivo Rossi" in t
    assert t.endswith("_Puoi copiarlo come resoconto per il cliente._")
    en = diary.build(store, "what did I get done for Rossi this week?", language="en")["text"]
    assert en.startswith("What you got done for **Mario Rossi** this week")


def test_the_diary_periods_and_an_empty_one(tmp_path):
    now = dt.datetime(2026, 11, 4, 15, 0).astimezone()  # a Wednesday
    assert diary.period("cosa ho fatto oggi", now)[0].date() == dt.date(2026, 11, 4)
    assert diary.period("cosa ho fatto ieri", now)[0].date() == dt.date(2026, 11, 3)
    start, end, it, _ = diary.period("cosa ho fatto la settimana scorsa", now)
    assert (start.date(), end.date(), it) == (dt.date(2026, 10, 26), dt.date(2026, 11, 2), "la settimana scorsa")
    assert diary.period("cosa ho fatto a ottobre", now)[2] == "a ottobre"
    assert diary.period("cosa ho fatto questa settimana", now)[0].date() == dt.date(2026, 11, 2)
    empty = diary.build(LifeStore(tmp_path / "e.db"), "cosa ho fatto ieri")
    assert empty["count"] == 0 and empty["text"].startswith("Non trovo niente di fatto ieri.")
    assert diary.asks("Cosa ho fatto questa settimana?") and diary.asks("what did I do yesterday?") and not diary.asks("cosa fai stasera?")


def test_the_diary_answers_in_chat_without_the_model(ws):
    store = life_store_for(ws)
    store.update_job(store.add_job("Bozza contratto")["id"], status="done")
    svc = ws.personal
    model = Quiet()
    svc._router_provider_override = model
    msg = svc.process_prompt(workspace_id=ws.name, prompt="cosa ho fatto questa settimana?")
    assert "- ✓ Bozza contratto" in msg.content and msg.content.startswith("Cosa hai fatto questa settimana")


# -- web search with the user's key -------------------------------------------------------------------------------------
class _Resp:
    def __init__(self, data):
        self.data = json.dumps(data).encode()

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_brave_and_tavily_results_are_parsed(monkeypatch):
    seen = []

    def fake(req, timeout=0):
        seen.append(req)
        if "brave" in req.full_url:
            return _Resp({"web": {"results": [{"title": "Museo <strong>Egizio</strong>", "url": "https://museoegizio.it", "description": "Aperto 9&ndash;18"}]}})
        return _Resp({"results": [{"title": "Orari", "url": "https://x.it", "content": "Dalle 9 alle 18"}]})

    monkeypatch.setattr(web_search.urllib.request, "urlopen", fake)
    b = BraveSearchBackend("k1").search("museo egizio orari", 3)
    assert b == [WebSearchResult(title="Museo Egizio", url="https://museoegizio.it", snippet="Aperto 9–18")]
    assert seen[0].get_header("X-subscription-token") == "k1"
    t = TavilySearchBackend("k2").search("museo egizio orari", 3)
    assert t[0].snippet == "Dalle 9 alle 18" and seen[1].get_header("Authorization") == "Bearer k2"


def test_the_users_key_is_used_before_duckduckgo(ws, monkeypatch):
    store = life_store_for(ws)
    ws.secret_store.store_secret(web_search.SECRET_REF, "test-key")
    store.update_settings(web_search_provider="brave")
    assert isinstance(web_search.keyed_backend(ws), BraveSearchBackend)

    calls = []
    monkeypatch.setattr(BraveSearchBackend, "search", lambda self, q, max_results=5, timeout=10.0: calls.append(("brave", q)) or
                        [WebSearchResult(title="Museo Egizio", url="https://museoegizio.it", snippet="Aperto dalle 9")])
    monkeypatch.setattr(web_search.DuckDuckGoSearchBackend, "search", lambda *a, **k: calls.append(("ddg",)) or [])

    class Plain(Quiet):
        def generate(self, messages, tools=None, output_schema=None):
            system = messages[0].content if messages else ""
            if "RESULTS:" in system:
                return SimpleNamespace(content="Apre alle 9 [1].")
            return super().generate(messages, tools, output_schema)

    svc = ws.personal
    svc._router_provider_override = Plain()
    answer = svc._web_answer("a che ora apre il museo egizio?", "museo egizio orari")
    assert calls == [("brave", "museo egizio orari")]
    assert answer.startswith("Apre alle 9 [1].") and "(https://museoegizio.it)" in answer


# -- "ho mandato il preventivo a Rossi": the open job is offered as done ------------------------------------------------------
def test_a_sentence_about_something_done_finds_the_open_job(tmp_path):
    from aether.life import completion

    store = LifeStore(tmp_path / "life.db")
    rossi = store.add_contact("Mario Rossi", kind="client")
    bianchi = store.add_contact("Bianchi", kind="client")
    quote = store.add_job("Inviare il preventivo", contact_id=rossi["id"])
    store.add_job("Preventivo cucina", contact_id=bianchi["id"])
    store.add_job("Logo nuovo")
    m = completion.match_open_job(store, "ho mandato il preventivo a Rossi")
    assert m["id"] == quote["id"] and m["contact_name"] == "Mario Rossi" and m["asked"] is True
    assert completion.match_open_job(store, "ho finito il logo")["asked"] is False
    assert completion.match_open_job(store, "ho mandato il preventivo") is None  # two quotes, nobody named: better to ask
    assert completion.match_open_job(store, "mando il preventivo a Rossi domani") is None  # not done yet
    assert completion.match_open_job(store, "ho mangiato una pizza") is None
    invoice = store.add_job("Send the invoice", contact_id=rossi["id"])
    assert completion.match_open_job(store, "I sent the invoice to Rossi")["id"] == invoice["id"]
    friday = dt.datetime(2026, 11, 6, 18, 0).astimezone()
    assert dt.datetime.fromtimestamp(completion.followup_due(friday)).strftime("%a %H:%M") == "Wed 09:00"  # three working days


def test_done_by_voice_ticks_the_job_asks_later_and_undo_reopens_it(ws):
    from aether.actions import undo as undo_mod

    store = life_store_for(ws)
    rossi = store.add_contact("Rossi", kind="client")
    job = store.add_job("Inviare il preventivo", contact_id=rossi["id"])
    svc = ws.personal
    svc._router_provider_override = Quiet()
    ask = svc.process_prompt(workspace_id=ws.name, prompt="ho mandato il preventivo a Rossi")
    assert ask.content.startswith("Segno come fatto **Inviare il preventivo** per **Rossi** e ") and "ti chiedo se ha risposto?" in ask.content
    assert store.get_job(job["id"])["status"] == "open", "nothing changes before the yes"
    done = svc.process_prompt(workspace_id=ws.name, prompt="sì", session_id=ask.session_id)
    assert done.content.startswith("Fatto: ho segnato come fatto **Inviare il preventivo**")
    assert store.get_job(job["id"])["status"] == "done"
    follow = [r for r in store.list_reminders() if r.get("job_id") == job["id"]]
    assert len(follow) == 1 and follow[0]["text"] == "Rossi ha risposto su: inviare il preventivo?" and follow[0]["due_at"]
    assert "✓ Inviare il preventivo" in diary.build(store, "cosa ho fatto per Rossi?")["text"]
    undo_mod.undo(ws, done.metadata["undo_execution_id"])
    assert store.get_job(job["id"])["status"] == "open" and not [r for r in store.list_reminders() if r.get("job_id") == job["id"]]


def test_a_follow_up_from_the_router_reads_as_a_question():
    from aether.personal.service import _note_sentence

    a = {"kind": "reminder", "title": "Laura ha risposto su: contratto?", "due_at": dt.datetime(2026, 11, 5, 9, 0).timestamp(), "due_has_time": True}
    s = _note_sentence(a, done=False)
    assert s.endswith("ti chiedo se **Laura** ha risposto su «contratto»") and "ha risposto su:" not in s
