"""Concentrazione: for a while Aether keeps its own nudges to itself (notifications stay in the bell, the desktop and Telegram are
quiet, the orb asks nothing), then tells you in a few sentences what arrived meanwhile.

Urgent notifications still get through. The window lives in the life settings (it survives a restart) and in a small process
registry the notification dispatcher reads without opening a database.
"""
from __future__ import annotations

import datetime as dt
import re
import threading
import time
from typing import Any

from aether.life.store import LifeStore

DEFAULT_MINUTES = 50
MAX_MINUTES = 8 * 60

_lock = threading.Lock()
_active: dict[str, tuple[float, float]] = {}  # workspace id -> (started_at, until)
_held: dict[str, list[str]] = {}  # workspace id -> titles of the notifications kept quiet


def is_active(workspace_id: str, now: float | None = None) -> bool:
    with _lock:
        win = _active.get(workspace_id)
    return bool(win) and win[0] <= (now or time.time()) < win[1]


def hold(workspace_id: str, title: str) -> None:
    """The dispatcher kept a notification quiet: remembered for the summary at the end."""
    with _lock:
        _held.setdefault(workspace_id, []).append(str(title or "").strip())


def start(store: LifeStore, workspace_id: str, minutes: int = DEFAULT_MINUTES, now: float | None = None) -> dict[str, Any]:
    minutes = max(5, min(int(minutes or DEFAULT_MINUTES), MAX_MINUTES))
    now = now or time.time()
    until = now + minutes * 60
    store.update_settings(focus_started=now, focus_until=until)
    with _lock:
        _active[workspace_id] = (now, until)
        _held[workspace_id] = []
    return status(store, workspace_id, now=now)


def status(store: LifeStore, workspace_id: str, now: float | None = None) -> dict[str, Any]:
    now = now or time.time()
    cfg = store.settings()
    started, until = float(cfg.get("focus_started") or 0), float(cfg.get("focus_until") or 0)
    if started and until > now:
        with _lock:  # after a restart the window is read back from the settings
            _active.setdefault(workspace_id, (started, until))
        return {"active": True, "started_at": started, "until": until, "remaining_s": int(until - now),
                "minutes": round((until - started) / 60), "held": len(_held.get(workspace_id, []))}
    return {"active": False, "started_at": started or None, "until": until or None, "remaining_s": 0,
            "ended": bool(started and until <= now), "held": len(_held.get(workspace_id, []))}


def stop(store: LifeStore, workspace_id: str) -> tuple[float, list[str]]:
    """Ends the window now (or confirms it has ended). Returns when it started and the notifications kept quiet."""
    started = float(store.settings().get("focus_started") or 0)
    store.update_settings(focus_started=0, focus_until=0)
    with _lock:
        _active.pop(workspace_id, None)
        held = _held.pop(workspace_id, [])
    return started, held


def summary(ws: Any, store: LifeStore, started: float, held: list[str], *, language: str = "it", until: float | None = None) -> str:
    """What arrived while you were concentrating, from facts only (the catch-up since the start of the window). `until` is the
    planned end: a window that ran out while Aether was closed lasted until then, not until it was reopened."""
    from aether.life import catchup

    en = str(language).lower().startswith("en")
    since = started or (time.time() - 3600)
    try:
        cu = catchup.for_workspace(ws, store, language=language, since=since)
        body = str(cu.get("body") or "")
        changes = int(cu.get("changes") or 0)
    except Exception:  # noqa: BLE001 - the end of the window is still announced
        body, changes = "", 0
    body = re.sub(r"^(Mentre eri via|While you were away):\s*", "", body)
    parts: list[str] = []
    if held:
        names = ", ".join(f"«{h}»" if not en else f"“{h}”" for h in held[:2] if h)
        parts.append((f"I kept {len(held)} notification{'s' if len(held) > 1 else ''} quiet" + (f": {names}" if names else "") + ".") if en else
                     (f"Ho tenuto in silenzio {'un avviso' if len(held) == 1 else f'{len(held)} avvisi'}" + (f": {names}" if names else "") + "."))
    if changes:
        parts.append(body[:1].upper() + body[1:])
    minutes = max(1, round((min(time.time(), until or time.time()) - since) / 60))
    head = (f"Focus over ({_dur(minutes, en)})." if en else f"Fine della concentrazione ({_dur(minutes, en)}).")
    if not parts:
        return head + (" Nothing arrived meanwhile." if en else " Nel frattempo non è arrivato niente.")
    return head + (" Meanwhile: " if en else " Nel frattempo: ") + " ".join(p[:1].lower() + p[1:] if i == 0 else p for i, p in enumerate(parts))


def _dur(minutes: int, en: bool) -> str:
    h, m = divmod(minutes, 60)
    if en:
        return " ".join(x for x in (f"{h} h" if h else "", f"{m} min" if m else "") if x)
    return " ".join(x for x in ((f"{h} {'ora' if h == 1 else 'ore'}") if h else "", (f"{m} {'minuto' if m == 1 else 'minuti'}") if m else "") if x)


# -- what you say -------------------------------------------------------------------------------------------------------

_START_RE = re.compile(
    r"\b(?:voglio\s+concentrarmi|devo\s+concentrarmi|fammi\s+concentrare|lasciami\s+concentrare|mi\s+concentro|"
    r"(?:avvia|attiva|inizia|metti)\s+(?:la\s+)?(?:modalit[aà]\s+)?(?:concentrazione|focus)|modalit[aà]\s+(?:concentrazione|focus)|"
    r"concentrazione\s+per|non\s+disturbarmi|non\s+voglio\s+essere\s+disturbat\w|"
    r"let\s+me\s+focus|i\s+need\s+to\s+focus|i\s+want\s+to\s+focus|focus\s+mode|start\s+focus|focus\s+for|do\s+not\s+disturb\s+me|don'?t\s+disturb\s+me)\b",
    re.I)
_STOP_RE = re.compile(
    r"\b(?:(?:fine|basta|termina|ferma|chiudi|stop|esci\s+dalla)\s+(?:la\s+)?(?:modalit[aà]\s+)?(?:concentrazione|focus)|"
    r"ho\s+finito\s+di\s+concentrarmi|(?:end|stop)\s+(?:the\s+)?focus|focus\s+(?:off|over))\b", re.I)
_DUR_RE = re.compile(r"(\d{1,3})\s*(?:(min\w*|m\b)|(or[ae]|h\b|hours?|hrs?))", re.I)


def parse(prompt: str) -> tuple[str, int] | None:
    """("start", minutes) | ("stop", 0) | None."""
    text = prompt or ""
    if _STOP_RE.search(text):
        return ("stop", 0)
    if not _START_RE.search(text):
        return None
    low = text.lower()
    m = _DUR_RE.search(low)
    if m:
        n = int(m.group(1))
        return ("start", n * 60 if m.group(3) else n)
    if re.search(r"mezz'?\s?ora|half\s+an\s+hour", low):
        return ("start", 30)
    if re.search(r"un\s+quarto\s+d'?\s?ora|quarter\s+of\s+an\s+hour", low):
        return ("start", 15)
    if re.search(r"un'?\s?ora|an\s+hour|one\s+hour", low):
        return ("start", 60)
    if re.search(r"due\s+ore|two\s+hours", low):
        return ("start", 120)
    return ("start", DEFAULT_MINUTES)


def started_text(st: dict[str, Any], en: bool) -> str:
    until = dt.datetime.fromtimestamp(float(st["until"])).strftime("%H:%M")
    if en:
        return (f"Focus on until {until}: I keep notifications and suggestions to myself (urgent ones still get through). "
                "When you are done I will tell you what arrived. Say “end focus” to stop earlier.")
    return (f"Concentrazione fino alle {until}: tengo per me avvisi e proposte, tranne quelli urgenti. "
            "Quando finisci ti dico cosa è arrivato. Di' «fine concentrazione» per smettere prima.")
