"""Il diario: "cosa ho fatto questa settimana?" / "cosa ho fatto per Rossi a ottobre?" answered from facts only, day by day.

Built from what you marked done (jobs, reminders), money that came in or went out, and what Aether did for you that stuck (mail
sent, appointments, issues: the Rewind timeline without what was undone). Useful to remember a week, or to write a client a
short report before an invoice. No model call: nothing is invented.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

from aether.life.store import LifeStore

_IT_DAYS = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
_EN_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_IT_MONTHS = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre")
_EN_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")

# what Aether did that is worth a line in your diary (reads and its own bookkeeping are left out)
_DONE_BY_AETHER = {
    "gmail.send": ("Mail sent", "Mail inviata"),
    "gmail.create_draft": ("Draft written", "Bozza scritta"),
    "calendar.create_event": ("Appointment set", "Appuntamento fissato"),
    "calendar.update_event": ("Appointment moved", "Appuntamento spostato"),
    "calendar.delete_event": ("Appointment cancelled", "Appuntamento cancellato"),
    "github.create_issue": ("Issue opened", "Issue aperta"),
}

_ASK_RE = re.compile(
    r"\b(?:cosa|che\s+cosa|che)\s+ho\s+(?:fatto|combinato|concluso|chiuso)\b|\bil\s+mio\s+diario\b|\bdiario\s+(?:di|della|del|dell')\b|"
    r"\bresoconto\s+(?:di|della|del|dell'|per)\b|\bwhat\s+(?:did\s+i|have\s+i)\s+(?:do|done|get\s+done|finish(?:ed)?|work(?:ed)?\s+on)\b|"
    r"\bmy\s+diary\b|\bwork\s+log\b", re.I)


def asks(prompt: str) -> bool:
    return bool(_ASK_RE.search(prompt or ""))


def period(prompt: str, now: dt.datetime | None = None) -> tuple[dt.datetime, dt.datetime, str, str]:
    """(start, end, Italian label, English label). This week (from Monday) unless the request says otherwise."""
    now = (now or dt.datetime.now().astimezone()).astimezone()
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    low = (prompt or "").lower()
    monday = day0 - dt.timedelta(days=day0.weekday())
    month0 = day0.replace(day=1)
    if re.search(r"\b(?:oggi|stamattina|today)\b", low):
        return day0, now, "oggi", "today"
    if re.search(r"\b(?:ieri|yesterday)\b", low):
        return day0 - dt.timedelta(days=1), day0, "ieri", "yesterday"
    if re.search(r"settimana\s+scorsa|scorsa\s+settimana|last\s+week", low):
        return monday - dt.timedelta(days=7), monday, "la settimana scorsa", "last week"
    if re.search(r"mese\s+scorso|scorso\s+mese|last\s+month", low):
        prev = (month0 - dt.timedelta(days=1)).replace(day=1)
        return prev, month0, f"a {_IT_MONTHS[prev.month - 1]}", f"in {_EN_MONTHS[prev.month - 1]}"
    if re.search(r"quest[oa]\s+mese|this\s+month", low):
        return month0, now, "questo mese", "this month"
    for i, (it, en) in enumerate(zip(_IT_MONTHS, _EN_MONTHS)):
        if re.search(rf"\b(?:{it}|{en.lower()})\b", low):
            year = now.year if i + 1 <= now.month else now.year - 1
            start = day0.replace(year=year, month=i + 1, day=1)
            end = (start + dt.timedelta(days=32)).replace(day=1)
            return start, min(end, now), f"a {it}", f"in {en}"
    if re.search(r"ultimi\s+(\d+)\s+giorni|last\s+(\d+)\s+days", low):
        n = int(next(g for g in re.search(r"ultimi\s+(\d+)\s+giorni|last\s+(\d+)\s+days", low).groups() if g))
        return day0 - dt.timedelta(days=max(1, min(n, 90)) - 1), now, f"gli ultimi {n} giorni", f"the last {n} days"
    return monday, now, "questa settimana", "this week"


def who(store: LifeStore, prompt: str) -> dict[str, Any] | None:
    """"…per Rossi", "…for Giulia", "…con Bianchi": a person Aether knows."""
    for m in re.finditer(r"\b(?:per|con|for|with)\s+(?:il\s+|la\s+|l'|lo\s+|the\s+)?([\wÀ-ÿ'’][\wÀ-ÿ'’.\- ]{1,40})", prompt or "", re.I):
        words = m.group(1).split()
        for n in range(min(3, len(words)), 0, -1):  # "Rossi questa settimana" → "Rossi"
            c = store.find_contact(" ".join(words[:n]))
            if c:
                return c
    return None


def _ts(v: Any) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def entries(store: LifeStore, start: float, end: float, *, contact: dict[str, Any] | None = None,
            timeline: list[dict[str, Any]] | None = None, en: bool = False) -> list[tuple[float, str]]:
    """(when, line) for everything done in [start, end), oldest first."""
    from aether.life.presence_brief import money_label

    cid = (contact or {}).get("id")
    names = {c["id"]: c["name"] for c in store.list_contacts()}
    out: list[tuple[float, str]] = []
    for j in store.list_jobs(status="done"):
        at = float(j.get("done_at") or 0)
        if start <= at < end and (not cid or j.get("contact_id") == cid):
            for_ = names.get(j.get("contact_id") or "")
            out.append((at, f"✓ {j['title']}" + (f" ({'for' if en else 'per'} {for_})" if for_ and not cid else "")))
    for r in store.list_reminders(include_done=True):
        at = float(r.get("done_at") or 0)
        if r.get("done") and start <= at < end and (not cid or r.get("contact_id") == cid):
            out.append((at, f"✓ {r['text'][:1].upper()}{r['text'][1:]}"))
    for m in store.list_money(status="paid", contact_id=cid):
        at = float(m.get("paid_at") or 0)
        if start <= at < end:
            amount = money_label(m["amount"], m["currency"]) + (f" ({m['what']})" if m.get("what") else "")
            name = names.get(m["contact_id"], "")
            verb = ("Paid by" if en else "Incassati da") if m["direction"] == "owed_to_me" else ("Paid to" if en else "Pagati a")
            out.append((at, f"€ {verb} {name}: {amount}" if name else f"€ {amount}"))
    for t in timeline or []:
        at = _ts(t.get("created_at"))
        label = _DONE_BY_AETHER.get(str(t.get("action_id") or ""))
        if not label or t.get("undone") or not (start <= at < end):
            continue
        title = str(t.get("title") or "").strip()
        if cid and not any(len(w) > 2 and w in title.lower() for w in str((contact or {}).get("name", "")).lower().split()):
            continue
        out.append((at, f"{label[0] if en else label[1]}" + (f": {title}" if title and title != t.get("action_id") else "")))
    return sorted(out, key=lambda x: x[0])


def build(store: LifeStore, prompt: str, *, language: str = "it", now: dt.datetime | None = None,
          timeline: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    en = str(language).lower().startswith("en")
    start, end, it_label, en_label = period(prompt, now)
    label = en_label if en else it_label
    contact = who(store, prompt)
    rows = entries(store, start.timestamp(), end.timestamp(), contact=contact, timeline=timeline, en=en)
    for_ = f" {'for' if en else 'per'} **{contact['name']}**" if contact else ""
    if not rows:
        text = (f"Nothing marked as done{for_} {label}. When you tick off jobs and reminders, or I do something for you, it shows up here."
                if en else f"Non trovo niente di fatto{for_} {label}. Quando segni come fatti lavori e promemoria, o faccio qualcosa per te, compare qui.")
        return {"text": text, "count": 0, "days": 0}
    days: dict[str, list[str]] = {}
    for at, line in rows:
        d = dt.datetime.fromtimestamp(at).astimezone()
        key = (f"{_EN_DAYS[d.weekday()]} {d.day} {_EN_MONTHS[d.month - 1]}" if en else f"{_IT_DAYS[d.weekday()]} {d.day} {_IT_MONTHS[d.month - 1]}")
        days.setdefault(key, []).append(line)
    head = (f"What you got done{for_} {label}: **{len(rows)}** thing{'s' if len(rows) != 1 else ''} in {len(days)} day{'s' if len(days) != 1 else ''}."
            if en else f"Cosa hai fatto{for_} {label}: **{len(rows)}** {'cosa' if len(rows) == 1 else 'cose'} in {len(days)} {'giorno' if len(days) == 1 else 'giorni'}.")
    body = "\n\n".join(f"**{k[:1].upper() + k[1:]}**\n" + "\n".join(f"- {x}" for x in v) for k, v in days.items())
    tail = ("_You can copy it as a report for the client._" if en else "_Puoi copiarlo come resoconto per il cliente._") if contact else ""
    return {"text": f"{head}\n\n{body}" + (f"\n\n{tail}" if tail else ""), "count": len(rows), "days": len(days)}


def for_workspace(ws: Any, store: LifeStore, prompt: str, *, language: str = "it") -> dict[str, Any]:
    timeline: list[dict[str, Any]] = []
    try:
        from aether.actions.undo import timeline as rewind

        timeline = rewind(ws, ws.id, limit=200)
    except Exception:  # noqa: BLE001 - the diary still has your own items
        timeline = []
    return build(store, prompt, language=language, timeline=timeline)
