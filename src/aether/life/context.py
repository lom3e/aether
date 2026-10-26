"""What the model is told about the user's own day before it answers: today's date (with the weekdays spelled out, so it never
counts), and the jobs, reminders and people saved in "Persone e lavori". Local data only, no network call, a few hundred tokens.

Without this the model answered "cosa devo fare questa settimana?" from the conversation alone, presenting things the user had
not confirmed as scheduled and naming the wrong weekdays.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from aether.core.dates import days_table

_MAX_JOBS, _MAX_REMINDERS, _MAX_PEOPLE = 15, 10, 25
_IT_DAYS = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
_IT_MONTHS = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre")


def _when(ts: float, now: dt.datetime, timed: bool = True) -> str:
    d = dt.datetime.fromtimestamp(ts).astimezone()
    day = f"{d.strftime('%A')} {d.strftime('%Y-%m-%d')}"
    late = " (OVERDUE)" if d < now else ""
    return f"{day}{' ' + d.strftime('%H:%M') if timed and (d.hour, d.minute) != (9, 0) else ''}{late}"


def today_line(now: dt.datetime, language: str = "it") -> str:
    if str(language).lower().startswith("it"):
        return f"Adesso è {_IT_DAYS[now.weekday()]} {now.day} {_IT_MONTHS[now.month - 1]} {now.year}, ore {now.strftime('%H:%M')}."
    return f"It is now {now.strftime('%A %B %-d %Y, %H:%M')}."


def user_context(ws: Any, *, now: dt.datetime | None = None, language: str = "it") -> str:
    now = (now or dt.datetime.now().astimezone()).astimezone()
    lines = [f"## Today\n{today_line(now, language)} Calendar of the next days (read dates from here, never count): {days_table(now)}."]
    try:
        from aether.life.store import life_store_for

        store = life_store_for(ws)
        jobs = store.list_jobs(status="open")
        rems = store.list_reminders()
        people = store.list_contacts()
    except Exception:  # noqa: BLE001 - no life store (tests, broken db): the date alone still helps
        return lines[0]
    by_id = {c["id"]: c["name"] for c in people}
    jobs.sort(key=lambda j: (j["due_at"] is None, j["due_at"] or 0))
    rems.sort(key=lambda r: (r["due_at"] is None, r["due_at"] or 0))
    rec = ["## The user's saved records (Persone e lavori)",
           "These are the ONLY saved jobs, reminders and people. Answer questions about the user's week, tasks or clients from "
           "them and the calendar; never present something as saved or scheduled if it is not listed here (offer to save it instead). "
           "When asked who someone is or what you know about the user, answer from these records and the memories above."]
    name = str((store.settings() or {}).get("user_name") or "").strip()
    if name:
        rec.append(f"The user's name: {name} (sign the user's mails with it; never sign as Aether).")
    rec.append("Open jobs:" + ("" if jobs else " none"))
    for j in jobs[:_MAX_JOBS]:
        who = by_id.get(j.get("contact_id") or "", "")
        rec.append(f"- {j['title']}" + (f" — for {who}" if who else "") + (f" — due {_when(j['due_at'], now, False)}" if j["due_at"] else ""))
    rec.append("Reminders:" + ("" if rems else " none"))
    for r in [x for x in rems if x.get("source") == "person"][:_MAX_REMINDERS]:
        rec.append(f"- {r['text']} — when {by_id.get(r.get('contact_id') or '', 'that person')} comes up (no date)")
    rems = [x for x in rems if x.get("source") != "person"]
    for r in rems[:_MAX_REMINDERS]:
        rec.append(f"- {r['text']}" + (f" — {_when(r['due_at'], now)}" if r["due_at"] else ""))
    rec.append("People:" + ("" if people else " none"))
    for c in people[:_MAX_PEOPLE]:
        extra = ", ".join(x for x in (c.get("company") or "", c.get("email") or "", c.get("phone") or "", (c.get("notes") or "")[:120]) if x)
        owed = [j["title"] for j in jobs if j.get("contact_id") == c["id"]][:3]
        rec.append(f"- {c['name']} ({c.get('kind') or 'person'})" + (f": {extra}" if extra else "") + (f"; open jobs: {', '.join(owed)}" if owed else ""))
    linked = connected_services(ws)
    rec.append("Connected services: " + (", ".join(linked) if linked else "none (calendar and mail are not readable until the user connects them in Collegamenti)"))
    return "\n".join(lines + ["\n".join(rec)])


def connected_services(ws: Any) -> list[str]:
    names = {"google_calendar": "Google Calendar", "gmail": "Gmail", "github": "GitHub", "telegram": "Telegram"}
    out = []
    try:
        svc = ws.connections
    except Exception:  # noqa: BLE001
        return out
    for key, label in names.items():
        try:
            conn = svc.get_connection(ws.id, key)
        except Exception:  # noqa: BLE001
            conn = None
        if conn and str(getattr(conn, "status", "")) in ("verified", "configured"):
            out.append(label)
    return out
