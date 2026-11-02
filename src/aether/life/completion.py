"""'Ho mandato il preventivo a Rossi': something you say you did that matches an open job is offered as done (one confirmation,
undoable), and when it was something sent or asked, Aether asks you in three working days whether they answered. This is what
fills the diary without ticking boxes."""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

from aether.life.store import LifeStore

_DONE_RE = re.compile(
    r"\b(?:ho|abbiamo)\s+(?:gi[aà]\s+|appena\s+|finalmente\s+)?(?P<it>mandat|inviat|spedit|fatt|finit|consegnat|chiamat|sentit|pagat|chius|"
    r"completat|terminat|scritt|chiest|preparat|sistemat|presentat|caricat|pubblicat)\w*|"
    r"\b(?:i(?:'ve|\s+have)?)\s+(?:just\s+|already\s+|finally\s+)?(?P<en>sent|did|done|finished|delivered|called|paid|closed|completed|wrote|asked|"
    r"prepared|fixed|submitted|uploaded|published)\b", re.I)
_ASKED = re.compile(r"^(?:mandat|inviat|spedit|chiest|presentat)|^(?:sent|asked|submitted)$", re.I)
_STOP = {"il", "lo", "la", "i", "gli", "le", "un", "una", "uno", "di", "a", "da", "in", "con", "su", "per", "tra", "fra", "del", "della", "dei",
         "delle", "al", "alla", "ai", "alle", "ho", "abbiamo", "gia", "già", "appena", "finalmente", "the", "a", "an", "to", "for", "of", "i",
         "have", "just", "already", "e", "and", "che", "oggi", "ieri", "today", "yesterday", "finally"}


def said_done(prompt: str) -> re.Match[str] | None:
    return _DONE_RE.search(prompt or "")


def _stems(text: str) -> set[str]:
    words = re.findall(r"[\wà-ÿ]+", (text or "").lower())
    return {w[:5] for w in words if len(w) >= 4 and w not in _STOP}


def match_open_job(store: LifeStore, prompt: str) -> dict[str, Any] | None:
    """The open job the sentence is about: a word of its title in the sentence (preventivo/preventivi), preferring the job of the
    person named. None when nothing matches or two jobs match equally (better to ask than to tick the wrong one)."""
    m = said_done(prompt)
    if not m:
        return None
    verb = (m.group("it") or m.group("en") or "").lower()
    said = _stems(prompt[m.end():] + " " + prompt[:m.start()]) - {verb[:5]}
    names = {c["id"]: c["name"] for c in store.list_contacts()}
    scored = []
    for j in store.list_jobs(status="open"):
        common = said & (_stems(j["title"]) - {verb[:5]})
        who = names.get(j.get("contact_id") or "", "")
        named = bool(who) and any(len(w) > 2 and re.search(rf"\b{re.escape(w)}\b", prompt, re.I) for w in who.split())
        if common:
            scored.append((len(common) + (2 if named else 0), -(j.get("due_at") or 9e12), j, who))
    if not scored:
        return None
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    best = scored[0]
    return {**best[2], "contact_name": best[3], "asked": bool(_ASKED.match(verb))}


def followup_due(now: dt.datetime | None = None, working_days: int = 3) -> float:
    """Three working days after today, at 09:00."""
    d = (now or dt.datetime.now().astimezone()).astimezone()
    left = working_days
    while left:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d.replace(hour=9, minute=0, second=0, microsecond=0).timestamp()
