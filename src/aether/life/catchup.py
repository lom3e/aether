""""Cosa mi sono perso?": when you come back after a few hours, what changed while you were away, in a few spoken sentences.

Built from facts only, no model call: what fell due, new mail that is not promotions or social, promises found in mail, what
Aether changed for you (Rewind), and the next appointment. When nothing changed it says so in one line.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from aether.life.store import LifeStore

logger = logging.getLogger(__name__)

AWAY_HOURS = 3


def mark_seen(store: LifeStore, at: float | None = None) -> float:
    """The app is in front of the user now. Returns how long they were away (hours); a long absence is remembered as `back_from`,
    so "cosa mi sono perso?" asked later still covers it."""
    now = at or dt.datetime.now().timestamp()
    last = float(store.settings().get("last_seen_at") or 0)
    away = (now - last) / 3600 if last else 0.0
    store.update_settings(last_seen_at=now, **({"back_from": last} if away >= AWAY_HOURS else {}))
    return away


def _sender(raw: str) -> str:
    name = (raw or "").split("<")[0].strip().strip('"')
    return name or (raw or "").strip("<>")


def build(ws: Any, store: LifeStore, *, language: str = "it", now: dt.datetime | None = None, since: float | None = None,
          gmail: Any = None, events: list[dict[str, Any]] | None = None, timeline: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    en = str(language).lower().startswith("en")
    now = (now or dt.datetime.now().astimezone()).astimezone()
    if since is None:  # the start of the last long absence, else the last twelve hours
        cfg = store.settings()
        since = float(cfg.get("back_from") or 0) or (now.timestamp() - 12 * 3600)
    since = float(since)
    away_h = (now.timestamp() - since) / 3600 if since else 0.0
    parts: list[str] = []

    fell_due = [x for x in store.list_jobs(status="open") + store.list_reminders()
                if x.get("due_at") and since < x["due_at"] <= now.timestamp()]
    if fell_due:
        first = str(fell_due[0].get("title") or fell_due[0].get("text"))
        parts.append((f"“{first}” fell due." if len(fell_due) == 1 else f"{len(fell_due)} things fell due, starting with “{first}”.") if en else
                     (f"È scaduto «{first}»." if len(fell_due) == 1 else f"Sono scadute {len(fell_due)} cose, la prima è «{first}»."))

    if gmail is not None and since:
        hours = max(1, int(away_h + 1))
        try:
            mails = gmail.search(query=f"in:inbox newer_than:{hours}h -category:promotions -category:social -category:updates", limit=10)
        except Exception as exc:  # noqa: BLE001 - mail is a nice-to-have here
            logger.info("catch-up mail lookup failed: %s", type(exc).__name__)
            mails = []
        if mails:
            who = []
            for m in mails:
                s = _sender(str(m.get("from") or ""))
                if s and s not in who:
                    who.append(s)
            names = ", ".join(who[:2])
            parts.append((f"{len(mails)} new mail{'s' if len(mails) > 1 else ''}" + (f", from {names}" if names else "") + ".") if en else
                         (f"{'Una mail nuova' if len(mails) == 1 else f'{len(mails)} mail nuove'}" + (f", da {names}" if names else "") + "."))

    found = [p for p in store.list_promises(status="new") if p["found_at"] > since]
    if found:
        p = found[0]
        parts.append(f"I found {len(found)} promise{'s' if len(found) > 1 else ''} in your mail, e.g. “{p['title']}”." if en else
                     f"Ho trovato {len(found)} {'promessa' if len(found) == 1 else 'promesse'} nelle mail, per esempio «{p['title']}».")

    done_by_me = [t for t in (timeline or []) if _ts(t.get("created_at")) > since and not t.get("undone")]
    if done_by_me:
        parts.append(f"I changed {len(done_by_me)} thing{'s' if len(done_by_me) > 1 else ''} for you: they are in Rewind." if en else
                     f"Ho cambiato {len(done_by_me)} {'cosa' if len(done_by_me) == 1 else 'cose'} per te: le trovi in Riavvolgi.")

    nxt = next((e for e in sorted(events or [], key=lambda e: e.get("start") or 0) if (e.get("start") or 0) >= now.timestamp()
                and e["start"] - now.timestamp() < 4 * 3600), None)
    if nxt:
        at = dt.datetime.fromtimestamp(nxt["start"]).strftime("%H:%M")
        parts.append(f"Next: {nxt['title']} at {at}." if en else f"Il prossimo impegno: {nxt['title']} alle {at}.")

    if not parts:
        body = "Nothing new while you were away." if en else "Mentre eri via non è successo niente di nuovo."
    else:
        body = " ".join(parts)
    lead = ("While you were away: " if en else "Mentre eri via: ") if parts else ""
    if lead:
        body = body[:1].lower() + body[1:]
    return {"text": lead + body, "body": lead + body, "offer": None, "away_hours": round(away_h, 1), "changes": len(parts), "moment": "catchup"}


def _ts(v: Any) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def for_workspace(ws: Any, store: LifeStore, *, language: str = "it") -> dict[str, Any]:
    """The catch-up with the user's real sources (Gmail when connected, today's calendar, Rewind)."""
    from aether.life import service as life

    gmail = None
    try:
        gmail = ws.connections.get_gmail_connector(ws.id)
    except Exception:  # noqa: BLE001
        gmail = None
    events: list[dict[str, Any]] = []
    try:
        raw, _ = life.fetch_events(ws)
        events = [e for e in (life._event_dict(x) for x in raw) if e]
    except Exception:  # noqa: BLE001
        events = []
    timeline: list[dict[str, Any]] = []
    try:
        from aether.actions.undo import timeline as rewind

        timeline = rewind(ws, ws.id, limit=30)
    except Exception:  # noqa: BLE001
        timeline = []
    return build(ws, store, language=language, gmail=gmail, events=events, timeline=timeline)
