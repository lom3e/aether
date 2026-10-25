"""What Aether says first when you open it: a short spoken brief built from facts (calendar, jobs, promises found in mail),
with at most ONE question at the end ("Hai promesso a Mario il preventivo per venerdì: vuoi che ti prepari la mail?").
No model call: it is instant, private and never invents anything. Saying yes runs the offer; nothing happens before.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from aether.life import service as life
from aether.life.store import LifeStore

_DAYS_IT = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
_MONTHS_IT = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre")


def _day(ts: float, now: dt.datetime, en: bool) -> str:
    d = dt.datetime.fromtimestamp(ts).astimezone().date()
    delta = (d - now.date()).days
    if delta == 0:
        return "today" if en else "oggi"
    if delta == 1:
        return "tomorrow" if en else "domani"
    if delta == -1:
        return "yesterday" if en else "ieri"
    if 1 < delta < 7:
        return d.strftime("%A") if en else _DAYS_IT[d.weekday()]
    return d.strftime("%B %-d") if en else f"il {d.day} {_MONTHS_IT[d.month - 1]}"


def _greeting(now: dt.datetime, en: bool) -> str:
    h = now.hour
    if en:
        return "Good morning." if 5 <= h < 13 else "Good afternoon." if h < 18 else "Good evening."
    return "Buongiorno." if 5 <= h < 13 else "Buon pomeriggio." if h < 18 else "Buonasera."


def ask_prompt(p: dict[str, Any], en: bool) -> str:
    """The request an `ask` offer runs: a draft reply for your promise, a friendly reminder for theirs."""
    who = p["who"] or ("them" if en else "lui/lei")
    if p["kind"] == "they_promised":
        return (f"Write {who} a short, friendly reminder email about: {p['title']}." if en else
                f"Scrivi a {who} una mail breve e gentile per ricordare: {p['title']}.")
    return (f"Draft a reply to {who} about the email “{p['subject']}”: {p['title']}." if en else
            f"Prepara una bozza di risposta a {who} sulla mail «{p['subject']}»: {p['title']}.")


def _offer(store: LifeStore, now: dt.datetime, en: bool, gmail_connected: bool) -> tuple[str, dict[str, Any] | None]:
    """The single question worth asking now, in priority order."""
    soon = (now + dt.timedelta(days=2)).timestamp()
    rows = store.list_promises()
    open_jobs = {j["id"] for j in store.list_jobs(status="open")}
    active = [r for r in rows if r["status"] in ("new", "tracked")]

    for r in active:  # a mail you sent seems to have closed a job
        if r["kind"] == "fulfilled" and r["status"] == "new" and r["job_id"] in open_jobs:
            return ((f"It looks like you already did “{r['title']}”. Shall I mark it as done?" if en else
                     f"Sembra che tu abbia già fatto «{r['title']}». Lo segno come fatto?"),
                    {"type": "job_done", "promise_id": r["id"]})
    for r in active:  # something you promised, due within two days (or late)
        if r["kind"] == "i_promised" and r["due_at"] and r["due_at"] <= soon and (not r["job_id"] or r["job_id"] in open_jobs):
            who, when = r["who"] or ("someone" if en else "qualcuno"), _day(r["due_at"], now, en)
            prompt = ask_prompt(r, en)
            return ((f"You promised {who}: “{r['title']}”, by {when}. Want me to draft the email?" if en else
                     f"Hai promesso a {who}: «{r['title']}», entro {when}. Vuoi che ti prepari la mail?"),
                    {"type": "ask", "promise_id": r["id"], "prompt": prompt})
    for r in active:  # someone owes you something and the date has passed
        if r["kind"] == "they_promised" and r["due_at"] and r["due_at"] < now.timestamp():
            who, when = r["who"] or ("someone" if en else "qualcuno"), _day(r["due_at"], now, en)
            prompt = ask_prompt(r, en)
            return ((f"{who} was going to “{r['title']}” by {when}, and nothing has arrived. Shall I write a friendly reminder?" if en else
                     f"{who} doveva: «{r['title']}», entro {when}, e non è ancora arrivato niente. Vuoi che scriva un sollecito gentile?"),
                    {"type": "ask", "promise_id": r["id"], "prompt": prompt})
    for r in active:  # someone asked you something you have not tracked yet
        if r["kind"] in ("they_asked", "i_promised") and r["status"] == "new":
            who = r["who"] or ("someone" if en else "qualcuno")
            line = (f"{who} asked you: “{r['title']}”." if r["kind"] == "they_asked" else f"You promised {who}: “{r['title']}”.") if en else \
                   (f"{who} ti ha chiesto: «{r['title']}»." if r["kind"] == "they_asked" else f"Hai promesso a {who}: «{r['title']}».")
            return (line + (" Shall I add it to your jobs?" if en else " Lo segno tra i lavori?"), {"type": "track", "promise_id": r["id"]})
    cfg = store.settings()
    if gmail_connected and not cfg.get("promise_watch") and not cfg.get("promise_watch_offered"):
        return (("Want me to check your mail every day for promises, yours and other people's, so nothing slips?" if en else
                 "Vuoi che ogni giorno controlli da solo le promesse nelle mail, le tue e quelle degli altri, così non ne sfugge nessuna?"),
                {"type": "watch_on"})
    return "", None


def _has_model(ws: Any) -> bool:
    try:
        from aether.providers.resolution import resolve_provider

        prov = resolve_provider(workspace=ws)
        return prov is not None and type(prov).__name__ != "UnresolvedProvider"
    except Exception:  # noqa: BLE001
        return False


def first_meeting(ws: Any, *, language: str = "it", now: dt.datetime | None = None, gmail_connected: bool = False,
                  has_model: bool | None = None) -> dict[str, Any]:
    """The very first time Aether opens: who it is, how to talk to it, and the one next step that makes it useful."""
    en = str(language).lower().startswith("en")
    now = (now or dt.datetime.now().astimezone()).astimezone()
    has_model = _has_model(ws) if has_model is None else has_model
    body = ("I'm Aether. Hold Space and talk to me, or write below. I look after your calendar, mail, people and promises, "
            "and before I change anything I always ask you." if en else
            "Sono Aether. Tieni premuto Spazio e parlami, oppure scrivimi qui sotto. Mi occupo di calendario, mail, persone e "
            "promesse, e prima di cambiare qualcosa te lo chiedo sempre.")
    offer: dict[str, Any] | None = None
    if not has_model:
        body += (" First, choose the model I think with: it takes a minute." if en else " Prima scegli il modello con cui ragiono: ci vuole un minuto.")
    elif not gmail_connected:
        body += (" Shall we connect Gmail and Google Calendar, so I can really help?" if en else
                 " Colleghiamo Gmail e Google Calendar, così posso aiutarti davvero?")
        offer = {"type": "open", "view": "connections"}
    greeting = _greeting(now, en)
    return {"text": f"{greeting} {body}", "body": body, "offer": offer, "date": now.strftime("%Y-%m-%d"), "first": True}


def build(ws: Any, store: LifeStore, *, language: str = "it", now: dt.datetime | None = None, events: list[dict[str, Any]] | None = None,
          gmail_connected: bool | None = None, first: bool = False) -> dict[str, Any]:
    en = str(language).lower().startswith("en")
    now = (now or dt.datetime.now().astimezone()).astimezone()
    if gmail_connected is None:
        try:
            ws.connections.get_gmail_connector(ws.id)
            gmail_connected = True
        except Exception:  # noqa: BLE001
            gmail_connected = False
    if first:
        return first_meeting(ws, language=language, now=now, gmail_connected=bool(gmail_connected))
    if events is None:
        events, _ = life.fetch_events(ws, now) if ws is not None else ([], "")
    today = life.build_today(store, now=now, events=events)
    parts = [_greeting(now, en)]
    upcoming = [e for e in today["events"] if e.get("all_day") or e["start"] >= now.timestamp() - 600]
    if upcoming:
        e = upcoming[0]
        at = "" if e.get("all_day") else dt.datetime.fromtimestamp(e["start"]).strftime("%H:%M")
        more = len(upcoming) - 1
        if en:
            parts.append((f"At {at} you have {e['title']}" if at else f"Today: {e['title']}") + (f", then {more} more." if more else "."))
        else:
            parts.append((f"Alle {at} hai {e['title']}" if at else f"Oggi hai {e['title']}") + (f", poi altri {more} impegni." if more > 1 else ", poi un altro impegno." if more else "."))
    overdue = today["jobs"]["overdue"] + today["reminders"]["overdue"]
    if overdue:
        first = overdue[0].get("title") or overdue[0].get("text")
        if en:
            parts.append(f"“{first}” is late." if len(overdue) == 1 else f"{len(overdue)} things are late, starting with “{first}”.")
        else:
            parts.append(f"«{first}» è in ritardo." if len(overdue) == 1 else f"Hai {len(overdue)} cose in ritardo, la prima è «{first}».")
    question, offer = _offer(store, now, en, bool(gmail_connected))
    if question:
        parts.append(question)
    elif len(parts) == 1:
        parts.append("Nothing urgent today." if en else "Oggi niente di urgente.")
    # text: what is said aloud; body: what is shown under the greeting the orb already displays
    return {"text": " ".join(parts), "body": " ".join(parts[1:]), "offer": offer, "date": now.strftime("%Y-%m-%d")}


def accept(ws: Any, store: LifeStore, offer: dict[str, Any], *, language: str = "it") -> dict[str, Any]:
    """Runs an offer the user said yes to. `ask` offers are run by the app as a normal request (with its own confirmation)."""
    en = str(language).lower().startswith("en")
    kind = offer.get("type")
    if kind == "watch_on":
        store.update_settings(promise_watch=True, promise_watch_offered=True)
        return {"text": "Done: I'll check your mail for promises every day." if en else "Fatto: controllerò le promesse nelle mail ogni giorno."}
    p = store.get_promise(str(offer.get("promise_id") or ""))
    if not p:
        raise ValueError("unknown promise")
    if kind == "job_done":
        if p["kind"] != "fulfilled" or not p["job_id"]:
            raise ValueError("not a fulfilled promise")
        job = store.update_job(p["job_id"], status="done")
        store.set_promise_status(p["id"], "done")
        try:
            life.sync_job(ws, store, job, language=language)
        except Exception:  # noqa: BLE001 - memory sync is a nicety
            pass
        return {"text": f"Marked as done: “{p['title']}”." if en else f"Segnato come fatto: «{p['title']}».", "job_id": p["job_id"]}
    if kind == "track":
        contact_id = None
        if p["who"]:
            c = store.find_contact(p["who"]) or store.add_contact(p["who"], kind="client" if p["kind"] in ("i_promised", "they_asked") else "person")
            contact_id = c["id"]
        job = store.add_job(p["title"], contact_id=contact_id, due_at=p["due_at"], source="promise_keeper")
        store.set_promise_status(p["id"], "tracked", job_id=job["id"])
        try:
            life.sync_job(ws, store, store.get_job(job["id"]) or job, language=language)
        except Exception:  # noqa: BLE001
            pass
        return {"text": f"Added to your jobs: “{p['title']}”." if en else f"Aggiunto ai lavori: «{p['title']}».", "job_id": job["id"]}
    if kind == "ask":
        store.set_promise_status(p["id"], "tracked")
        return {"text": "", "prompt": offer.get("prompt") or ask_prompt(p, en)}
    raise ValueError("unknown offer")


def decline(store: LifeStore, offer: dict[str, Any]) -> None:
    """'No' to an offer: it is not asked again (a promise you said no to stays visible in the panel)."""
    if offer.get("type") == "watch_on":
        store.update_settings(promise_watch_offered=True)
        return
    p = store.get_promise(str(offer.get("promise_id") or ""))
    if p and p["status"] == "new":
        store.set_promise_status(p["id"], "ignored" if p["kind"] in ("fulfilled", "they_asked") else "tracked")
