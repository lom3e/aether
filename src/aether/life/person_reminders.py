"""Reminders tied to a person, not to a time: "quando sento Mario ricordami di chiedergli la fattura".

They come back when the person does: as soon as you mention them to Aether, and in the morning brief when today's calendar
has something with them ("Alle 15 vedi Mario: chiedergli la fattura"). Once said in chat they are marked done; the brief only
mentions them (you may not meet the person after all).
"""
from __future__ import annotations

import re
from typing import Any

SOURCE = "person"


def _names(contact: dict[str, Any]) -> list[str]:
    full = str(contact.get("name") or "").strip()
    if not full:
        return []
    first = full.split()[0]
    return [full] + ([first] if first != full and len(first) >= 3 else [])


def _mentions(text: str, contact: dict[str, Any]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text or "", re.IGNORECASE) for n in _names(contact))


def pending(store: Any) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """(reminder, contact) for every open person reminder."""
    people = {c["id"]: c for c in store.list_contacts()}
    return [(r, people[r["contact_id"]]) for r in store.list_reminders() if r.get("source") == SOURCE and r.get("contact_id") in people]


def due_in_text(store: Any, text: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [(r, c) for r, c in pending(store) if _mentions(text, c)]


def touch_mentioned(store: Any, text: str) -> None:
    """Talking about someone counts as hearing from them (the "you haven't heard from X" nudge waits)."""
    for c in store.list_contacts():
        if _mentions(text, c):
            store.touch_contact(c["id"])


def surface_in_chat(store: Any, prompt: str, english: bool = False) -> str:
    """The line appended to Aether's answer when the user mentions someone with a pending reminder; marks them done."""
    hits = due_in_text(store, prompt)
    if not hits:
        return ""
    lines = []
    for r, c in hits:
        store.complete_reminder(r["id"])
        lines.append(f"📌 You asked me to remind you when {c['name']} came up: **{r['text']}**." if english else
                     f"📌 Mi avevi chiesto di ricordartelo quando si parlava di {c['name']}: **{r['text']}**.")
    return "\n\n".join(lines)


def for_events(store: Any, events: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    """(reminder, contact, event) for today's events that involve the person (by name in the title)."""
    out = []
    for r, c in pending(store):
        ev = next((e for e in events if _mentions(str(e.get("title") or ""), c)), None)
        if ev:
            out.append((r, c, ev))
    return out
