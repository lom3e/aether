"""Life service: keeps contacts/jobs mirrored into the assistant's memory (so answers can use them) and builds the Today view."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Callable

from aether.life.store import LifeStore

logger = logging.getLogger(__name__)

SOON_DAYS = 7


# -- memory mirroring ---------------------------------------------------------------------------------------------------
def _memory_api(ws: Any):
    mem = getattr(ws, "memory", None)
    return mem if mem is not None and hasattr(mem, "create_memory") else None


def _upsert_memory(ws: Any, memory_id: str | None, category: str, summary: str, content: str, source_id: str) -> str | None:
    mem = _memory_api(ws)
    if mem is None:
        return None
    from aether.memory.models import WorkforceMemory

    try:
        if memory_id:
            try:
                mem.update_memory(memory_id=memory_id, summary=summary, content=content, workspace_id=ws.id)
                return memory_id
            except KeyError:
                pass
        rec = WorkforceMemory.create(
            workspace_id=ws.id, category=category, summary=summary, content=content,
            provenance={"source_entity": "life", "source_id": source_id, "verification_status": "verified"},
            tags=["life"],
        )
        return mem.create_memory(rec).id
    except Exception as exc:  # noqa: BLE001 - the memory mirror must never break saving a contact or a job
        logger.warning("life memory mirror failed: %s", type(exc).__name__)
        return memory_id


def _drop_memory(ws: Any, memory_id: str | None) -> None:
    mem = _memory_api(ws)
    if mem is None or not memory_id:
        return
    try:
        mem.delete_memory(memory_id, hard=True, workspace_id=ws.id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("life memory drop failed: %s", type(exc).__name__)


def _fmt_due(ts: float | None) -> str:
    return dt.datetime.fromtimestamp(ts).astimezone().strftime("%Y-%m-%d") if ts else ""


def sync_contact(ws: Any, store: LifeStore, contact: dict[str, Any]) -> None:
    lines = [f"{contact['name']} ({contact['kind']})"]
    for label, key in (("Company", "company"), ("Notes", "notes")):
        if contact.get(key):
            lines.append(f"{label}: {contact[key]}")
    mid = _upsert_memory(ws, contact.get("memory_id"), "person", f"{contact['name']} ({contact['kind']})", "\n".join(lines), contact["id"])
    if mid != contact.get("memory_id"):
        store.set_memory_id("contacts", contact["id"], mid)


def sync_job(ws: Any, store: LifeStore, job: dict[str, Any]) -> None:
    who = f" for {job['contact_name']}" if job.get("contact_name") else ""
    due = f", due {_fmt_due(job.get('due_at'))}" if job.get("due_at") else ""
    state = "done" if job["status"] == "done" else "open"
    summary = f"Job{who}: {job['title']}"
    mid = _upsert_memory(ws, job.get("memory_id"), "project", summary, f"{summary}{due} ({state}).{(' ' + job['notes']) if job.get('notes') else ''}", job["id"])
    if mid != job.get("memory_id"):
        store.set_memory_id("jobs", job["id"], mid)


def forget_contact(ws: Any, store: LifeStore, contact_id: str) -> bool:
    c = store.get_contact(contact_id)
    ok = store.delete_contact(contact_id)
    if c:
        _drop_memory(ws, c.get("memory_id"))
    return ok


def forget_job(ws: Any, store: LifeStore, job_id: str) -> bool:
    j = store.get_job(job_id)
    ok = store.delete_job(job_id)
    if j:
        _drop_memory(ws, j.get("memory_id"))
    return ok


# -- Today --------------------------------------------------------------------------------------------------------------
def _event_dict(e: dict[str, Any]) -> dict[str, Any] | None:
    start = (e.get("start") or {})
    raw = start.get("dateTime") or start.get("date") if isinstance(start, dict) else e.get("start_time") or e.get("start")
    if not raw:
        return None
    try:
        when = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.astimezone()
    return {"title": e.get("summary") or e.get("title") or "(no title)", "start": when.timestamp(), "location": e.get("location") or "",
            "all_day": bool(isinstance(start, dict) and start.get("date") and not start.get("dateTime"))}


def build_today(store: LifeStore, *, now: dt.datetime | None = None, events: list[dict[str, Any]] | None = None, pending_approvals: int = 0,
                calendar_error: str = "") -> dict[str, Any]:
    now = (now or dt.datetime.now().astimezone()).astimezone()
    sod = now.replace(hour=0, minute=0, second=0, microsecond=0)
    eod = sod + dt.timedelta(days=1)
    soon = eod + dt.timedelta(days=SOON_DAYS)
    s, e, w = sod.timestamp(), eod.timestamp(), soon.timestamp()

    jobs = store.list_jobs(status="open")
    overdue = [j for j in jobs if j["due_at"] and j["due_at"] < s]
    today = [j for j in jobs if j["due_at"] and s <= j["due_at"] < e]
    upcoming = [j for j in jobs if j["due_at"] and e <= j["due_at"] < w]
    undated = [j for j in jobs if not j["due_at"]]
    rems = store.list_reminders()
    rem_overdue = [r for r in rems if r["due_at"] and r["due_at"] < s]
    rem_today = [r for r in rems if r["due_at"] and s <= r["due_at"] < e]
    rem_undated = [r for r in rems if not r["due_at"]]
    evs = sorted((x for x in (_event_dict(ev) for ev in (events or [])) if x and s <= x["start"] < e), key=lambda x: x["start"])
    out = {
        "date": sod.strftime("%Y-%m-%d"), "events": evs, "calendar_error": calendar_error,
        "jobs": {"overdue": overdue, "today": today, "upcoming": upcoming, "undated": undated[:5]},
        "reminders": {"overdue": rem_overdue, "today": rem_today, "undated": rem_undated[:5]},
        "pending_approvals": pending_approvals,
    }
    out["counts"] = {"events": len(evs), "overdue": len(overdue) + len(rem_overdue), "today": len(today) + len(rem_today), "upcoming": len(upcoming)}
    out["empty"] = not any((evs, overdue, today, upcoming, rem_overdue, rem_today, pending_approvals))
    return out


def brief_text(today: dict[str, Any], language: str = "it") -> str:
    """A short plain-text morning brief (also used as the notification body). Facts only, no filler."""
    en = (language or "").lower().startswith("en")
    c = today["counts"]
    parts: list[str] = []
    if en:
        if c["events"]:
            parts.append(f"{c['events']} appointment(s): " + "; ".join(f"{dt.datetime.fromtimestamp(e['start']).strftime('%H:%M')} {e['title']}" for e in today["events"][:4]))
        if c["overdue"]:
            parts.append(f"{c['overdue']} overdue")
        if today["jobs"]["today"] or today["reminders"]["today"]:
            parts.append("due today: " + "; ".join([f"{j['title']}" + (f" ({j['contact_name']})" if j.get("contact_name") else "") for j in today["jobs"]["today"]] + [r["text"] for r in today["reminders"]["today"]]))
        if today["pending_approvals"]:
            parts.append(f"{today['pending_approvals']} waiting for your approval")
        return " · ".join(parts) or "Nothing scheduled for today."
    if c["events"]:
        parts.append(f"{c['events']} appuntament{'o' if c['events'] == 1 else 'i'}: " + "; ".join(f"{dt.datetime.fromtimestamp(e['start']).strftime('%H:%M')} {e['title']}" for e in today["events"][:4]))
    if c["overdue"]:
        parts.append(f"{c['overdue']} in ritardo")
    if today["jobs"]["today"] or today["reminders"]["today"]:
        parts.append("da fare oggi: " + "; ".join([f"{j['title']}" + (f" ({j['contact_name']})" if j.get("contact_name") else "") for j in today["jobs"]["today"]] + [r["text"] for r in today["reminders"]["today"]]))
    if today["pending_approvals"]:
        parts.append(f"{today['pending_approvals']} in attesa della tua approvazione")
    return " · ".join(parts) or "Niente in programma per oggi."


def fetch_events(ws: Any, now: dt.datetime | None = None) -> tuple[list[dict[str, Any]], str]:
    """Today's calendar events through the existing `calendar.list_events` action (read-only). Returns (events, error)."""
    executor = getattr(ws, "action_executor", None)
    if executor is None:
        return [], ""
    now = (now or dt.datetime.now().astimezone()).astimezone()
    sod = now.replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        ex = executor.execute("calendar.list_events", ws.id, {"time_min": sod.isoformat(), "time_max": (sod + dt.timedelta(days=1)).isoformat(), "limit": 25})
        out = getattr(ex, "output_data", None) or {}
        err = getattr(ex, "error_message", None) or ""
        return list(out.get("events") or []), ("" if out.get("events") is not None else str(err)[:160])
    except Exception as exc:  # noqa: BLE001 - a missing/expired calendar must not break Today
        return [], type(exc).__name__
