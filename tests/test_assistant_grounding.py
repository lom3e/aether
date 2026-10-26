"""What the October audit found, fixed: a weekday the user says lands on that weekday, "sì"/"no" after a confirmation card act
like the buttons (the model used to answer "Fatto" while nothing was saved), the model sees today's date and the user's
saved records instead of developer docs, a mail is written in full without Gmail, "apri Spotify" opens it, the weather is
answered from Open-Meteo, and Groq's per-minute limit falls over to the sibling model instead of a silent 20 s wait."""
from __future__ import annotations

import datetime as dt
import json
import urllib.error
from types import SimpleNamespace

import pytest

from aether.core import dates
from aether.core.context import prepare_execution_context
from aether.life import context as life_context
from aether.life import weather
from aether.life.store import LifeStore, life_store_for
from aether.personal import mac_open
from aether.workspace.workspace import Workspace

MON = dt.datetime(2026, 10, 26, 21, 0).astimezone()


class Model:
    def __init__(self, payload):
        self.payload = payload

    def generate(self, messages):
        return SimpleNamespace(content=json.dumps(self.payload))


# -- dates ------------------------------------------------------------------------------------------------------------------
def test_a_weekday_the_user_said_wins_over_the_model_counting():
    saturday = dt.datetime(2026, 10, 31, 9, 0).astimezone()
    assert dates.fix_weekday("entro venerdì", saturday, MON).date() == dt.date(2026, 10, 30)
    assert dates.fix_weekday("venerdì della settimana prossima", saturday, MON).date() == dt.date(2026, 11, 6)
    assert dates.fix_weekday("by Friday", saturday, MON).date() == dt.date(2026, 10, 30)
    assert dates.fix_weekday("il 31 ottobre", saturday, MON) == saturday, "an explicit date is kept"
    assert dates.fix_weekday("lunedì o martedì", saturday, MON) == saturday, "two weekdays: no guess"
    assert dates.fix_weekday("venerdì", saturday, MON).hour == 9, "the time of day is kept"
    assert "Friday 2026-10-30" in dates.days_table(MON)


def test_the_router_fixes_a_wrong_friday(tmp_path):
    from aether.personal import tool_router

    r = tool_router.route("Rossi vuole il preventivo entro venerdì", now=MON,
                          provider=Model({"action": "life_note", "note_kind": "job", "title": "Inviare il preventivo",
                                          "contact_name": "Rossi", "due": "2026-10-31"}))
    assert dt.datetime.fromtimestamp(r["due_at"]).date() == dt.date(2026, 10, 30)


# -- what the model is told -------------------------------------------------------------------------------------------------
def test_the_model_sees_today_and_the_saved_records_not_developer_docs(tmp_path):
    ws = Workspace.init(tmp_path, name="grounding")
    try:
        store = life_store_for(ws)
        c = store.add_contact("Mario Rossi", kind="client")
        store.add_job("Mandare il preventivo del sito", contact_id=c["id"], due_at=dt.datetime(2026, 10, 30, 9, 0).astimezone().timestamp())
        store.add_reminder("Chiamare Laura", due_at=dt.datetime(2026, 10, 27, 10, 0).astimezone().timestamp())
        text = life_context.user_context(ws, now=MON)
        assert "lunedì 26 ottobre 2026" in text and "Friday 2026-10-30" in text
        assert "- Mandare il preventivo del sito — for Mario Rossi — due Friday 2026-10-30" in text
        assert "- Chiamare Laura — Tuesday 2026-10-27 10:00" in text
        assert "Mario Rossi (client); open jobs: Mandare il preventivo del sito" in text
        assert "Connected services: none" in text

        prep = prepare_execution_context("quanto fa 3+4?", workspace=ws, workspace_id=ws.id)
        system = prep.messages[0].content
        assert "The user's saved records" in system and "Mario Rossi" in system
        assert "what-is-aether.md" not in system and "Internal Workforce" not in system
        assert len(system) < 6000
    finally:
        ws.close()


# -- yes / no after a confirmation card ----------------------------------------------------------------------------------------
def test_yes_saves_and_no_cancels_like_the_buttons(tmp_path):
    ws = Workspace.init(tmp_path, name="yes-no")
    try:
        svc = ws.personal
        store = life_store_for(ws)
        svc._router_provider_override = Model({"action": "life_note", "note_kind": "reminder", "title": "Chiamare Laura",
                                               "due": (dt.datetime.now() + dt.timedelta(days=1)).strftime("%Y-%m-%dT10:00")})
        card = svc.process_prompt(workspace_id=ws.name, prompt="ricordami domani alle 10 di chiamare Laura")
        assert card.metadata["status"] == "proposal_pending" and store.list_reminders() == []
        done = svc.process_prompt(workspace_id=ws.name, prompt="sì", session_id=card.session_id)
        assert done.content.startswith("Fatto"), done.content
        assert [r["text"] for r in store.list_reminders()] == ["Chiamare Laura"], "the spoken yes really saved it"

        svc._router_provider_override = Model({"action": "life_note", "note_kind": "contact", "contact_name": "Giulia Verdi"})
        card2 = svc.process_prompt(workspace_id=ws.name, prompt="aggiungi Giulia Verdi come cliente", session_id=card.session_id)
        assert card2.metadata["status"] == "proposal_pending"
        no = svc.process_prompt(workspace_id=ws.name, prompt="no, lascia stare", session_id=card.session_id)
        assert no.content == "Va bene, non faccio niente." and no.metadata["status"] == "proposal_declined"
        assert store.list_contacts() == []
        assert str(svc.store.get_proposal(card2.metadata["proposal_id"], workspace_id=ws.id).status.value) == "revoked"
    finally:
        ws.close()


def test_a_mail_without_gmail_is_written_not_planned(tmp_path):
    ws = Workspace.init(tmp_path, name="mail-text")
    try:
        svc = ws.personal
        svc._router_provider_override = Model({"action": "mail_compose", "contact_name": "Mario", "instructions": "preventivo giovedì"})
        intent = svc.classify_intent("scrivi una mail a Mario per dirgli che il preventivo arriva giovedì", recent_history=[])
        assert intent.action_id == "email.send"  # the old keyword rule
        msg = svc.process_prompt(workspace_id=ws.name, prompt="scrivi una mail a Mario per dirgli che il preventivo arriva giovedì")
        assert msg.metadata.get("status") != "proposal_pending" and "Cosa farò" not in (msg.content or "")
    finally:
        ws.close()


# -- open apps and sites ------------------------------------------------------------------------------------------------------
APPS = {"spotify": "/Applications/Spotify.app", "calculator": "/System/Applications/Calculator.app", "notes": "/System/Applications/Notes.app",
        "safari": "/Applications/Safari.app"}


@pytest.mark.parametrize("prompt,expected", [
    ("apri Spotify", ("app", "/Applications/Spotify.app")),
    ("Apri la calcolatrice", ("app", "/System/Applications/Calculator.app")),
    ("lancia safari per favore", ("app", "/Applications/Safari.app")),
    ("open notes", ("app", "/System/Applications/Notes.app")),
    ("apri youtube", ("url", "https://www.youtube.com")),
    ("apri github.com", ("url", "https://github.com")),
])
def test_open_finds_installed_apps_and_sites(prompt, expected):
    assert mac_open.resolve(mac_open.parse(prompt), APPS) == expected


@pytest.mark.parametrize("prompt", ["apri una issue su aether", "apri il calendario di domani", "apri la mail di Mario", "ciao"])
def test_other_requests_are_not_taken_for_open(prompt):
    assert mac_open.parse(prompt) is None


def test_open_runs_with_an_argument_list_and_only_web_urls(monkeypatch):
    calls = []
    monkeypatch.setattr(mac_open.shutil, "which", lambda n: "/usr/bin/open")
    monkeypatch.setattr(mac_open.sys, "platform", "darwin")
    monkeypatch.setattr(mac_open.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or SimpleNamespace(returncode=0))
    assert mac_open.open_target("app", "/Applications/Spotify.app")
    assert not mac_open.open_target("url", "file:///etc/passwd")
    assert calls == [["/usr/bin/open", "-a", "/Applications/Spotify.app"]]


# -- weather --------------------------------------------------------------------------------------------------------------------
GEO = {"results": [{"name": "Milano", "latitude": 45.46, "longitude": 9.19, "timezone": "Europe/Rome"}]}
FC = {"current": {"temperature_2m": 9.9, "weather_code": 2},
      "daily": {"weather_code": [3, 61], "temperature_2m_min": [6.2, 7.4], "temperature_2m_max": [15.1, 12.6], "precipitation_probability_max": [10, 80]}}


def test_weather_remembers_the_city_and_answers_in_one_breath(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(weather, "_get", lambda url, ws, purpose: seen.append(purpose) or (GEO if "geocoding" in url else FC))
    store = LifeStore(tmp_path / "life.db")
    assert "Per quale città" in weather.answer(None, store, "che tempo fa?")
    assert weather.answer(None, store, "che tempo fa a Milano?") == \
        "A Milano adesso ci sono 10 gradi, poco nuvoloso; oggi tra 6 e 15. Domani pioggia debole, tra 7 e 13."
    assert store.settings()["home_city"] == "Milano"
    assert weather.answer(None, store, "domani piove?") == "Domani a Milano: pioggia debole, tra 7 e 13 gradi. Meglio portare l'ombrello."
    assert weather.brief_line(None, store) == "A Milano ci sono 10 gradi, poco nuvoloso, massima 15."
    assert set(seen) == {"weather_place", "weather_forecast"}
    assert weather.asks_weather("che tempo fa domani?") and not weather.asks_weather("che ore sono?")


def test_weather_offline_says_so(tmp_path, monkeypatch):
    def down(url, ws, purpose):
        raise weather.WeatherError("network")

    monkeypatch.setattr(weather, "_get", down)
    store = LifeStore(tmp_path / "life.db")
    store.update_settings(home_city="Milano")
    assert weather.answer(None, store, "che tempo fa?") == "Adesso non riesco a raggiungere il servizio meteo."
    assert weather.brief_line(None, store) == ""


# -- Groq ---------------------------------------------------------------------------------------------------------------------------
def test_groq_answers_with_the_sibling_model_instead_of_waiting(monkeypatch):
    from aether.providers import groq_provider as gp
    from aether.providers.errors import RateLimitError

    prov = gp.GroqProvider.__new__(gp.GroqProvider)
    prov.config = SimpleNamespace(base_url="https://api.groq.com/openai/v1", timeout=30, model="openai/gpt-oss-120b", temperature=None, max_tokens=None, api_key="x")
    monkeypatch.setattr(prov, "_headers", lambda: {})
    sent = []

    class Resp:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"model": self.body["model"], "choices": [{"message": {"content": "ok"}}]}).encode()

    def once(req, timeout):
        body = json.loads(req.data)
        sent.append(body["model"])
        if body["model"] == "openai/gpt-oss-120b":
            raise RateLimitError("429", provider="groq", retry_after=19.0)
        return Resp(body)

    monkeypatch.setattr(prov, "_open_once", once)
    monkeypatch.setattr(gp.time, "sleep", lambda s: pytest.fail("must not wait when the sibling answers"))
    body = prov._build_body([SimpleNamespace(role="user", content="ciao", images=None, tool_calls=None)], None, None, stream=False)
    assert body["reasoning_effort"] == "low"
    assert prov._post_json("/chat/completions", body)["model"] == "openai/gpt-oss-20b"
    assert sent == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
