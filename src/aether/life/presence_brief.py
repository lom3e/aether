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


def _greeting(now: dt.datetime, en: bool, name: str = "") -> str:
    h = now.hour
    if en:
        word = "Good morning" if 5 <= h < 13 else "Good afternoon" if h < 18 else "Good evening"
    else:
        word = "Buongiorno" if 5 <= h < 13 else "Buon pomeriggio" if h < 18 else "Buonasera"
    return f"{word}, {name}." if name else f"{word}."


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
    money = _money_offer(store, now, en)
    if money:
        return money
    reconnect = _reconnect_offer(store, now, en)
    if reconnect:
        return reconnect
    cfg = store.settings()
    if gmail_connected and not cfg.get("promise_watch") and not cfg.get("promise_watch_offered"):
        return (("Want me to check your mail every day for promises, yours and other people's, so nothing slips?" if en else
                 "Vuoi che ogni giorno controlli da solo le promesse nelle mail, le tue e quelle degli altri, così non ne sfugge nessuna?"),
                {"type": "watch_on"})
    return "", None


MONEY_NUDGE_DAYS = 7
RECONNECT_DAYS = 21


def money_label(amount: float, currency: str = "EUR") -> str:
    n = f"{float(amount):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".").removesuffix(",00")
    return f"{n} €" if (currency or "EUR") == "EUR" else f"{n} {currency}"


def _money_offer(store: LifeStore, now: dt.datetime, en: bool) -> tuple[str, dict[str, Any] | None] | None:
    """Someone has owed you money for a week (and Aether has not asked about it this week): a polite reminder, written for you."""
    people = {c["id"]: c for c in store.list_contacts()}
    week = MONEY_NUDGE_DAYS * 86400
    for m in store.list_money(status="open"):
        if m["direction"] != "owed_to_me" or now.timestamp() - m["created_at"] < week or (m.get("nudged_at") and now.timestamp() - m["nudged_at"] < week):
            continue
        who = people.get(m["contact_id"], {}).get("name") or ("someone" if en else "qualcuno")
        days = int((now.timestamp() - m["created_at"]) // 86400)
        amount, what = money_label(m["amount"], m["currency"]), m.get("what") or ""
        prompt = (f"Write {who} a short, kind reminder about the {amount}" + (f" for {what}" if what else "") + " they owe me." if en else
                  f"Scrivi a {who} un sollecito breve e gentile per i {amount}" + (f" di {what}" if what else "") + " che mi deve.")
        return ((f"{who} has owed you {amount} for {days} days. Shall I write a kind reminder?" if en else
                 f"{who} ti deve {amount} da {days} giorni. Vuoi che prepari un sollecito gentile?"),
                {"type": "money_nudge", "money_id": m["id"], "prompt": prompt})
    return None


def _reconnect_offer(store: LifeStore, now: dt.datetime, en: bool) -> tuple[str, dict[str, Any] | None] | None:
    """A client you worked with and have not heard of for three weeks: two lines to keep the relationship warm."""
    asked = dict(store.settings().get("reconnect_offered") or {})
    worked = {j["contact_id"] for j in store.list_jobs() if j.get("contact_id")}
    for c in sorted(store.list_contacts(), key=lambda c: c.get("last_seen_at") or 0):
        seen = c.get("last_seen_at") or c.get("created_at") or 0
        if c.get("kind") != "client" or c["id"] not in worked or now.timestamp() - seen < RECONNECT_DAYS * 86400:
            continue
        if now.timestamp() - float(asked.get(c["id"], 0)) < 30 * 86400:
            continue
        weeks = int((now.timestamp() - seen) // (7 * 86400))
        first = c["name"].split()[0]
        prompt = (f"Write {c['name']} two warm, short lines to hear how things are going (no sales pitch)." if en else
                  f"Scrivi a {c['name']} due righe calde e brevi per sentire come va (niente tono commerciale).")
        return ((f"You haven't heard from {first} in {weeks} weeks. Shall I write two lines to see how it's going?" if en else
                 f"Non senti {first} da {weeks} settimane. Le scrivo due righe per sentire come va?"),
                {"type": "reconnect", "contact_id": c["id"], "prompt": prompt})
    return None


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
          gmail_connected: bool | None = None, first: bool = False, with_weather: bool = True) -> dict[str, Any]:
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
    parts = [_greeting(now, en, str((store.settings() or {}).get("user_name") or "").split(" ")[0])]
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
    from aether.life.person_reminders import for_events

    for r, c, ev in for_events(store, upcoming)[:2]:  # "Alle 15:00 vedi Mario: chiedergli la fattura."
        at = "" if ev.get("all_day") else dt.datetime.fromtimestamp(ev["start"]).strftime("%H:%M")
        parts.append((f"At {at} you see {c['name']}: remember “{r['text']}”." if at else f"Today you see {c['name']}: remember “{r['text']}”.") if en else
                     (f"Alle {at} vedi {c['name']}: ricordati «{r['text']}»." if at else f"Oggi vedi {c['name']}: ricordati «{r['text']}»."))
    question, offer = _offer(store, now, en, bool(gmail_connected))
    if question:
        parts.append(question)
    elif len(parts) == 1:
        parts.append("Nothing urgent today." if en else "Oggi niente di urgente.")
    if with_weather:  # right after the greeting: "A Milano ci sono 10 gradi, sereno, massima 15."
        from aether.life import weather

        line = weather.brief_line(ws, store, language)
        if line:
            parts.insert(1, line)
    # text: what is said aloud; body: what is shown under the greeting the orb already displays
    return {"text": " ".join(parts), "body": " ".join(parts[1:]), "offer": offer, "date": now.strftime("%Y-%m-%d")}


def _still_open_today(store: LifeStore, now: dt.datetime) -> list[tuple[str, dict[str, Any]]]:
    """("job"|"reminder", item) due today or earlier and not done (person reminders have no date and never count)."""
    eod = (now.replace(hour=0, minute=0, second=0, microsecond=0) + dt.timedelta(days=1)).timestamp()
    jobs = [("job", j) for j in store.list_jobs(status="open") if j["due_at"] and j["due_at"] < eod]
    rems = [("reminder", r) for r in store.list_reminders() if r["due_at"] and r["due_at"] < eod]
    return sorted(jobs + rems, key=lambda x: x[1]["due_at"])


def _done_today(store: LifeStore, now: dt.datetime) -> int:
    sod = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    jobs = sum(1 for j in store.list_jobs(status="done") if (j.get("done_at") or 0) >= sod)
    rems = sum(1 for r in store.list_reminders(include_done=True) if r["done"] and (r.get("done_at") or 0) >= sod)
    return jobs + rems


def evening(ws: Any, store: LifeStore, *, language: str = "it", now: dt.datetime | None = None) -> dict[str, Any]:
    """The close of the day: what got done, what is still open, and one question: move what is left to tomorrow?"""
    en = str(language).lower().startswith("en")
    now = (now or dt.datetime.now().astimezone()).astimezone()
    name = str((store.settings() or {}).get("user_name") or "").split(" ")[0]
    parts = [_greeting(now, en, name)]
    done = _done_today(store, now)
    if done:
        parts.append(f"Today you closed {done} thing{'s' if done > 1 else ''}." if en else
                     f"Oggi hai chiuso {done} {'cosa' if done == 1 else 'cose'}.")
    if now.weekday() == 4:  # Friday evening: the week in two sentences before the usual close
        parts.extend(_week_lines(store, now, en))
    left = _still_open_today(store, now)
    offer = None
    if left:
        titles = [str(x.get("title") or x.get("text")) for _, x in left[:3]]
        quoted = ", ".join(f"“{t}”" if en else f"«{t}»" for t in titles) + (" …" if len(left) > 3 else "")
        if en:
            parts.append(f"{'One thing is' if len(left) == 1 else f'{len(left)} things are'} still open: {quoted}. Shall I move {'it' if len(left) == 1 else 'them'} to tomorrow?")
        else:
            parts.append(f"{'Resta aperta una cosa' if len(left) == 1 else f'Restano aperte {len(left)} cose'}: {quoted}. {'La sposto' if len(left) == 1 else 'Le sposto'} a domani?")
        offer = {"type": "roll_over", "items": [[k, x["id"]] for k, x in left[:20]]}
    elif done or len(parts) > 1:
        parts.append("Nothing left open: the day is closed." if en else "Non resta niente in sospeso: giornata chiusa.")
    else:  # nothing done and nothing open: no point in talking
        return {"text": "", "body": "", "offer": None, "date": now.strftime("%Y-%m-%d"), "moment": "evening"}
    return {"text": " ".join(parts), "body": " ".join(parts[1:]), "offer": offer, "date": now.strftime("%Y-%m-%d"), "moment": "evening"}


def _week_lines(store: LifeStore, now: dt.datetime, en: bool) -> list[str]:
    """What the week closed, and the first things of next week (by day)."""
    monday = (now - dt.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    closed = sum(1 for j in store.list_jobs(status="done") if (j.get("done_at") or 0) >= monday)
    closed += sum(1 for r in store.list_reminders(include_done=True) if r["done"] and (r.get("done_at") or 0) >= monday)
    next_mon = monday + 7 * 86400
    ahead = [(x["due_at"], str(x.get("title") or x.get("text"))) for x in store.list_jobs(status="open") + store.list_reminders()
             if x.get("due_at") and next_mon <= x["due_at"] < next_mon + 7 * 86400]
    ahead.sort()
    out = []
    if closed:
        out.append(f"This week you closed {closed} thing{'s' if closed > 1 else ''}." if en else
                   f"Questa settimana hai chiuso {closed} {'cosa' if closed == 1 else 'cose'}.")
    if ahead:
        days = [(_day(ts, now, en), t) for ts, t in ahead[:3]]
        listed = "; ".join(f"{d} {t}" if en else f"{d} «{t}»" for d, t in days)
        out.append(f"Next week: {listed}." if en else f"La settimana prossima: {listed}.")
    return out


def roll_over(store: LifeStore, items: list[Any], now: dt.datetime | None = None) -> int:
    """Moves the given open items to tomorrow, keeping their time of day (a late item without a real time goes to 9:00)."""
    now = (now or dt.datetime.now().astimezone()).astimezone()
    tomorrow = (now + dt.timedelta(days=1)).date()
    moved = 0
    for kind, item_id in items:
        item = store.get_job(item_id) if kind == "job" else store.get_reminder(item_id) if kind == "reminder" else None
        if not item or not item.get("due_at") or (kind == "job" and item["status"] != "open") or (kind == "reminder" and item["done"]):
            continue
        old = dt.datetime.fromtimestamp(item["due_at"]).astimezone()
        new = dt.datetime(tomorrow.year, tomorrow.month, tomorrow.day, old.hour, old.minute).astimezone().timestamp()
        if kind == "job":
            store.update_job(item_id, due_at=new)
        else:
            store.set_reminder_due(item_id, new)
        moved += 1
    return moved


def accept(ws: Any, store: LifeStore, offer: dict[str, Any], *, language: str = "it") -> dict[str, Any]:
    """Runs an offer the user said yes to. `ask` offers are run by the app as a normal request (with its own confirmation)."""
    en = str(language).lower().startswith("en")
    kind = offer.get("type")
    if kind == "money_nudge":
        store.mark_money_nudged(str(offer.get("money_id") or ""))
        return {"text": "", "prompt": offer.get("prompt") or ""}
    if kind == "reconnect":
        _mark_reconnect(store, str(offer.get("contact_id") or ""))
        return {"text": "", "prompt": offer.get("prompt") or ""}
    if kind == "roll_over":
        n = roll_over(store, list(offer.get("items") or []))
        return {"text": ("Done: moved to tomorrow. Have a good evening." if en else "Fatto: spostate a domani. Buona serata.") if n else
                ("Nothing left to move." if en else "Non c'era più niente da spostare.")}
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


def _mark_reconnect(store: LifeStore, contact_id: str) -> None:
    asked = dict(store.settings().get("reconnect_offered") or {})
    asked[contact_id] = dt.datetime.now().timestamp()
    store.update_settings(reconnect_offered=asked)


def decline(store: LifeStore, offer: dict[str, Any]) -> None:
    """'No' to an offer: it is not asked again (a promise you said no to stays visible in the panel)."""
    if offer.get("type") == "watch_on":
        store.update_settings(promise_watch_offered=True)
        return
    if offer.get("type") == "roll_over":  # nothing to remember: they stay where they are
        return
    if offer.get("type") == "money_nudge":
        store.mark_money_nudged(str(offer.get("money_id") or ""))
        return
    if offer.get("type") == "reconnect":
        _mark_reconnect(store, str(offer.get("contact_id") or ""))
        return
    p = store.get_promise(str(offer.get("promise_id") or ""))
    if p and p["status"] == "new":
        store.set_promise_status(p["id"], "ignored" if p["kind"] in ("fulfilled", "they_asked") else "tracked")
