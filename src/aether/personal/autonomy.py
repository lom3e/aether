"""Earned autonomy: Aether asks before every change; after you approved the same kind of change a few times in a row it
offers to do that kind on its own from now on. You grant it once, per kind, and can take it back any time; everything
it then does alone still shows up in Rewind with Undo.

A "kind" is narrow on purpose: "move the Zalando mail to the Trash", "save a job in People & jobs", "create a calendar
event", never "anything in Gmail". Sending mail and deleting events are never eligible.
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

OFFER_AFTER = 3
ELIGIBLE = {"gmail.trash", "gmail.modify_labels", "gmail.create_draft", "life.save", "google_calendar.create_event", "google_calendar.update_event"}


def key_for(action_id: str, args: dict[str, Any] | None) -> str | None:
    """The kind of change an action is, or None when it can never be done alone."""
    a = args or {}
    if action_id not in ELIGIBLE:
        return None
    if action_id in ("gmail.trash", "gmail.modify_labels"):
        q = re.sub(r"\s+", " ", str(a.get("query") or "")).strip().lower()
        if not q:
            return None
        return f"{action_id}|{a.get('op', 'trash')}|{q}"
    if action_id == "life.save":
        return f"life.save|{a.get('kind', '')}"
    return action_id


def label_for(action_id: str, args: dict[str, Any] | None) -> str:
    a = args or {}
    if action_id == "gmail.trash":
        return f"spostare nel cestino le mail «{a.get('query', '')}»"
    if action_id == "gmail.modify_labels":
        return f"{'archiviare' if a.get('op') == 'archive' else 'segnare come lette'} le mail «{a.get('query', '')}»"
    if action_id == "gmail.create_draft":
        return "salvare bozze di risposta in Gmail (senza inviarle)"
    if action_id == "life.save":
        return {"job": "segnare i lavori dei clienti", "reminder": "salvare promemoria", "contact": "salvare nuovi contatti"}.get(str(a.get("kind")), "salvare in Persone e lavori")
    if action_id == "google_calendar.create_event":
        return "creare eventi nel calendario"
    if action_id == "google_calendar.update_event":
        return "spostare eventi nel calendario"
    return action_id


class AutonomyStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS autonomy (
                key TEXT PRIMARY KEY, label TEXT NOT NULL DEFAULT '', streak INTEGER NOT NULL DEFAULT 0,
                granted_at TEXT, declined_at TEXT, revoked_at TEXT, offered_at TEXT, runs INTEGER NOT NULL DEFAULT 0)""")

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    @staticmethod
    def _now() -> str:
        return dt.datetime.now(dt.timezone.utc).isoformat()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM autonomy WHERE key = ?", (key,)).fetchone()
        return dict(row) if row else None

    def granted(self, key: str | None) -> bool:
        row = self.get(key) if key else None
        return bool(row and row["granted_at"] and not row["revoked_at"])

    def note_approved(self, key: str, label: str) -> dict[str, Any] | None:
        """A human approved one change of this kind. Returns an offer {key, label, count} when it is time to ask."""
        with self._lock, self._conn() as c:
            c.execute("INSERT OR IGNORE INTO autonomy (key, label) VALUES (?, ?)", (key, label))
            c.execute("UPDATE autonomy SET streak = streak + 1, label = ? WHERE key = ?", (label, key))
            row = dict(c.execute("SELECT * FROM autonomy WHERE key = ?", (key,)).fetchone())
            due = row["streak"] >= OFFER_AFTER and not row["granted_at"] and not row["declined_at"] and not row["offered_at"]
            if due:
                c.execute("UPDATE autonomy SET offered_at = ? WHERE key = ?", (self._now(), key))
        return {"key": key, "label": label, "count": row["streak"]} if due else None

    def note_ran_alone(self, key: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("UPDATE autonomy SET runs = runs + 1 WHERE key = ?", (key,))

    def reset(self, key: str | None) -> None:
        """A rejection or an Undo: the streak starts over (a granted autonomy stays, the user can revoke it)."""
        if not key:
            return
        with self._lock, self._conn() as c:
            c.execute("UPDATE autonomy SET streak = 0, offered_at = NULL WHERE key = ? AND granted_at IS NULL", (key,))

    def decide(self, key: str, allow: bool) -> dict[str, Any] | None:
        with self._lock, self._conn() as c:
            c.execute("INSERT OR IGNORE INTO autonomy (key) VALUES (?)", (key,))
            if allow:
                c.execute("UPDATE autonomy SET granted_at = ?, revoked_at = NULL, declined_at = NULL WHERE key = ?", (self._now(), key))
            else:
                c.execute("UPDATE autonomy SET declined_at = ?, granted_at = NULL WHERE key = ?", (self._now(), key))
        return self.get(key)

    def revoke(self, key: str) -> bool:
        with self._lock, self._conn() as c:
            cur = c.execute("UPDATE autonomy SET revoked_at = ?, streak = 0, offered_at = NULL WHERE key = ? AND granted_at IS NOT NULL AND revoked_at IS NULL",
                            (self._now(), key))
            return cur.rowcount > 0

    def list_granted(self) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM autonomy WHERE granted_at IS NOT NULL AND revoked_at IS NULL ORDER BY granted_at DESC").fetchall()
        return [dict(r) for r in rows]


def autonomy_store_for(workspace: Any) -> AutonomyStore:
    def factory() -> AutonomyStore:
        return AutonomyStore(Path(workspace.conversations_db_path).parent / "autonomy.db")

    getter = getattr(workspace, "_get_or_create", None)
    return getter("autonomy_store", factory) if getter else factory()
