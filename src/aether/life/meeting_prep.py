"""Ready for the meeting: about ten minutes before an appointment with someone Aether knows, one notification with what matters
about them: what you owe them, what they owe you (work or money), what you asked to be reminded of, a promise found in mail and
the last mail exchanged. Facts only, no model call, and nothing at all when there is nothing to say.

People are recognised by name in the event title ("Call con Mario") or by their email among the invited.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Any

from aether.life.store import LifeStore

logger = logging.getLogger(__name__)

LEAD_MIN, LEAD_MAX = 5 * 60, 15 * 60  # notify when the meeting starts in 5 to 15 minutes


def _start(ev: dict[str, Any]) -> float | None:
    start = ev.get("start")
    raw = ev.get("start_time") or (start.get("dateTime") if isinstance(start, dict) else start)
    if isinstance(raw, (int, float)):
        return float(raw)
    if not raw or "T" not in str(raw):
        return None  # all-day events have no "ten minutes before"
    try:
        d = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d if d.tzinfo else d.astimezone()).timestamp()


def people_in(store: LifeStore, ev: dict[str, Any]) -> list[dict[str, Any]]:
    title = str(ev.get("title") or ev.get("summary") or "")
    emails = {str(a.get("email") or "").lower() for a in (ev.get("attendees") or []) if a.get("email")}
    out = []
    for c in store.list_contacts():
        names = [c["name"]] + ([c["name"].split()[0]] if len(c["name"].split()) > 1 and len(c["name"].split()[0]) >= 3 else [])
        if (c.get("email") and c["email"].lower() in emails) or any(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", title, re.I) for n in names):
            out.append(c)
    return out


def brief_for(store: LifeStore, ev: dict[str, Any], *, gmail: Any = None, language: str = "it") -> str:
    """What to know before this meeting, or "" when Aether knows nothing useful about the people in it."""
    from aether.life.presence_brief import money_label

    en = str(language).lower().startswith("en")
    lines: list[str] = []
    for c in people_in(store, ev)[:3]:
        name = c["name"]
        jobs = [j["title"] for j in store.list_jobs(status="open", contact_id=c["id"])][:2]
        if jobs:
            lines.append(f"For {name} you have open: " + "; ".join(jobs) + "." if en else f"Per {name} hai aperto: " + "; ".join(f"«{t}»" for t in jobs) + ".")
        for m in store.list_money(status="open", contact_id=c["id"])[:2]:
            amount = money_label(m["amount"], m["currency"]) + (f" ({m['what']})" if m.get("what") else "")
            lines.append((f"{name} owes you {amount}." if m["direction"] == "owed_to_me" else f"You owe {name} {amount}.") if en else
                         (f"{name} ti deve {amount}." if m["direction"] == "owed_to_me" else f"Devi {amount} a {name}."))
        for r in [r for r in store.list_reminders() if r.get("contact_id") == c["id"] and r.get("source") == "person"][:2]:
            lines.append(f"You wanted to remember: {r['text']}." if en else f"Volevi ricordarti: «{r['text']}».")
        first = name.split()[0].lower()
        for p in [p for p in store.list_promises() if p["status"] in ("new", "tracked") and first in (p.get("who") or "").lower()][:1]:
            lines.append((f"Promise: {p['title']}." if en else f"Promessa: «{p['title']}».") if p["kind"] != "they_promised" else
                         (f"{name} promised: {p['title']}." if en else f"{name} aveva promesso: «{p['title']}»."))
        if gmail is not None and c.get("email"):
            try:
                last = gmail.search(query=f"(from:{c['email']} OR to:{c['email']}) newer_than:60d", limit=1)
            except Exception as exc:  # noqa: BLE001
                logger.info("meeting prep mail lookup failed: %s", type(exc).__name__)
                last = []
            if last:
                lines.append(f"Last mail: “{last[0].get('subject') or '(no subject)'}”." if en else f"Ultima mail: «{last[0].get('subject') or '(senza oggetto)'}».")
    return " ".join(lines)


def tick(ws: Any, store: LifeStore, *, now: dt.datetime | None = None, events: list[dict[str, Any]] | None = None, gmail: Any = None,
         language: str = "it") -> list[str]:
    """Called every minute: notifies once per meeting starting in 5-15 minutes when there is something to say. Returns the event ids notified."""
    now = (now or dt.datetime.now().astimezone()).astimezone()
    if events is None:
        try:
            ex = ws.action_executor.execute("calendar.list_events", ws.id, {"time_min": now.isoformat(), "time_max": (now + dt.timedelta(minutes=20)).isoformat(), "limit": 10})
            events = list((getattr(ex, "output_data", None) or {}).get("events") or [])
        except Exception:  # noqa: BLE001 - no calendar: nothing to prepare
            return []
        try:
            gmail = ws.connections.get_gmail_connector(ws.id)
        except Exception:  # noqa: BLE001
            gmail = None
    done = dict(store.settings().get("prepped_events") or {})
    sent = []
    for ev in events:
        st, eid = _start(ev), str(ev.get("id") or f"{ev.get('title')}@{ev.get('start_time')}")
        if st is None or eid in done or not (LEAD_MIN <= st - now.timestamp() <= LEAD_MAX):
            continue
        text = brief_for(store, ev, gmail=gmail, language=language)
        done[eid] = now.timestamp()
        if not text:
            continue
        mins = int(round((st - now.timestamp()) / 60))
        title = f"Tra {mins} minuti: {ev.get('title') or ''}" if language.startswith("it") else f"In {mins} minutes: {ev.get('title') or ''}"
        try:
            ws.notifications.notify(ws.id, "insight", title, text, link_view="home")
        except Exception:  # noqa: BLE001
            logger.debug("meeting prep notification failed", exc_info=True)
        sent.append(eid)
    week_ago = now.timestamp() - 7 * 86400
    store.update_settings(prepped_events={k: v for k, v in done.items() if v > week_ago})
    return sent
