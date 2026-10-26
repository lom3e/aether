"""SQLite store for contacts (people and clients), jobs and reminders. Local, one file next to the other workspace databases.

Times are epoch seconds (UTC). Nothing here talks to the network and nothing here decides anything: it only stores what the user
(or the user's confirmed capture) put in, so every row can be shown, edited and forgotten.
"""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

CONTACT_KINDS = ("client", "person", "company")
JOB_STATUSES = ("open", "done")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'person', company TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
    memory_id TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, contact_id TEXT, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', due_at REAL,
    notes TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT 'manual', memory_id TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
    done_at REAL
);
CREATE TABLE IF NOT EXISTS reminders (
    id TEXT PRIMARY KEY, contact_id TEXT, job_id TEXT, text TEXT NOT NULL, due_at REAL, done INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'manual', created_at REAL NOT NULL, done_at REAL
);
CREATE TABLE IF NOT EXISTS life_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS promises (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, who TEXT NOT NULL DEFAULT '', due_at REAL,
    message_id TEXT NOT NULL DEFAULT '', subject TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'new',
    job_id TEXT, found_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_due ON jobs(status, due_at);
CREATE INDEX IF NOT EXISTS reminders_due ON reminders(done, due_at);
"""

_CONTACT_FIELDS = ("name", "kind", "company", "email", "phone", "notes")
_JOB_FIELDS = ("contact_id", "title", "status", "due_at", "notes")


class LifeStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return _Conn(conn)

    # -- settings (all opt-in, off by default) ---------------------------------------------------------------
    DEFAULT_SETTINGS = {"brief_enabled": False, "brief_time": "08:30", "last_brief_date": "",
                        "promise_watch": False, "last_promise_scan": 0.0, "promise_watch_offered": False,
                        "home_city": ""}

    def settings(self) -> dict[str, Any]:
        import json

        out = dict(self.DEFAULT_SETTINGS)
        with self._lock, self._conn() as c:
            for r in c.execute("SELECT key, value FROM life_settings"):
                try:
                    out[r["key"]] = json.loads(r["value"])
                except ValueError:
                    pass
        return out

    def update_settings(self, **values: Any) -> dict[str, Any]:
        import json
        import re

        if "brief_time" in values and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(values["brief_time"])):
            raise ValueError("brief_time must be HH:MM")
        with self._lock, self._conn() as c:
            for k, v in values.items():
                if k in self.DEFAULT_SETTINGS and v is not None:
                    c.execute("INSERT INTO life_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, json.dumps(v)))
        return self.settings()

    # -- contacts ---------------------------------------------------------------------------------------------
    def add_contact(self, name: str, *, kind: str = "person", company: str = "", email: str = "", phone: str = "", notes: str = "") -> dict[str, Any]:
        name = (name or "").strip()
        if not name:
            raise ValueError("a contact needs a name")
        if kind not in CONTACT_KINDS:
            raise ValueError(f"kind must be one of {CONTACT_KINDS}")
        now = time.time()
        cid = f"ct-{uuid.uuid4().hex[:10]}"
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO contacts(id,name,kind,company,email,phone,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (cid, name[:200], kind, company.strip()[:200], email.strip()[:200], phone.strip()[:60], notes.strip()[:4000], now, now))
        return self.get_contact(cid) or {}

    def get_contact(self, contact_id: str) -> dict[str, Any] | None:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM contacts WHERE id=?", (contact_id,)).fetchone()
        return dict(r) if r else None

    def find_contact(self, name: str) -> dict[str, Any] | None:
        """Case-insensitive exact name, then a unique 'starts with / contains' match (never a guess between several)."""
        n = (name or "").strip().lower()
        if not n:
            return None
        rows = self.list_contacts()
        exact = [r for r in rows if r["name"].lower() == n]
        if len(exact) == 1:
            return exact[0]
        partial = [r for r in rows if n in r["name"].lower() or r["name"].lower() in n]
        return partial[0] if len(partial) == 1 else None

    def list_contacts(self, kind: str | None = None) -> list[dict[str, Any]]:
        q, args = "SELECT * FROM contacts", []
        if kind:
            q += " WHERE kind=?"
            args.append(kind)
        with self._lock, self._conn() as c:
            return [dict(r) for r in c.execute(q + " ORDER BY name COLLATE NOCASE", args)]

    def update_contact(self, contact_id: str, **fields: Any) -> dict[str, Any] | None:
        sets = {k: v for k, v in fields.items() if k in _CONTACT_FIELDS and v is not None}
        if "kind" in sets and sets["kind"] not in CONTACT_KINDS:
            raise ValueError(f"kind must be one of {CONTACT_KINDS}")
        if "name" in sets and not str(sets["name"]).strip():
            raise ValueError("a contact needs a name")
        if sets:
            cols = ", ".join(f"{k}=?" for k in sets)
            with self._lock, self._conn() as c:
                c.execute(f"UPDATE contacts SET {cols}, updated_at=? WHERE id=?", [*sets.values(), time.time(), contact_id])
        return self.get_contact(contact_id)

    def set_memory_id(self, table: str, row_id: str, memory_id: str | None) -> None:
        if table not in ("contacts", "jobs"):
            raise ValueError("bad table")
        with self._lock, self._conn() as c:
            c.execute(f"UPDATE {table} SET memory_id=? WHERE id=?", (memory_id, row_id))

    def delete_contact(self, contact_id: str) -> bool:
        with self._lock, self._conn() as c:
            n = c.execute("DELETE FROM contacts WHERE id=?", (contact_id,)).rowcount
            c.execute("UPDATE jobs SET contact_id=NULL WHERE contact_id=?", (contact_id,))
            c.execute("UPDATE reminders SET contact_id=NULL WHERE contact_id=?", (contact_id,))
        return n > 0

    # -- promises found in mail (promise keeper) ----------------------------------------------------------------
    # kinds: i_promised (you owe someone), they_asked (someone asked you), they_promised (someone owes you),
    # fulfilled (a sent mail seems to close an open job: job_id). status: new | tracked | ignored | done
    PROMISE_KINDS = ("i_promised", "they_asked", "they_promised", "fulfilled")
    PROMISE_STATUSES = ("new", "tracked", "ignored", "done")

    def add_promise(self, kind: str, title: str, *, who: str = "", due_at: float | None = None, message_id: str = "",
                    subject: str = "", job_id: str | None = None) -> dict[str, Any]:
        if kind not in self.PROMISE_KINDS:
            raise ValueError(f"kind must be one of {self.PROMISE_KINDS}")
        if not (title or "").strip():
            raise ValueError("a promise needs a title")
        now = time.time()
        pid = f"pm-{uuid.uuid4().hex[:10]}"
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO promises(id,kind,title,who,due_at,message_id,subject,status,job_id,found_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (pid, kind, title.strip()[:300], (who or "").strip()[:120], due_at, message_id[:200], (subject or "")[:300], "new", job_id, now, now))
        return self.get_promise(pid) or {}

    def get_promise(self, promise_id: str) -> dict[str, Any] | None:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM promises WHERE id=?", (promise_id,)).fetchone()
        return dict(r) if r else None

    def list_promises(self, *, status: str | None = None) -> list[dict[str, Any]]:
        q, args = "SELECT * FROM promises", []
        if status:
            q += " WHERE status=?"
            args.append(status)
        with self._lock, self._conn() as c:
            return [dict(r) for r in c.execute(q + " ORDER BY (due_at IS NULL), due_at, found_at DESC", args)]

    def set_promise_status(self, promise_id: str, status: str, *, job_id: str | None = None) -> dict[str, Any] | None:
        if status not in self.PROMISE_STATUSES:
            raise ValueError(f"status must be one of {self.PROMISE_STATUSES}")
        with self._lock, self._conn() as c:
            if job_id:
                c.execute("UPDATE promises SET status=?, job_id=?, updated_at=? WHERE id=?", (status, job_id, time.time(), promise_id))
            else:
                c.execute("UPDATE promises SET status=?, updated_at=? WHERE id=?", (status, time.time(), promise_id))
        return self.get_promise(promise_id)

    # -- jobs -------------------------------------------------------------------------------------------------
    def add_job(self, title: str, *, contact_id: str | None = None, due_at: float | None = None, notes: str = "", source: str = "manual") -> dict[str, Any]:
        title = (title or "").strip()
        if not title:
            raise ValueError("a job needs a title")
        if contact_id and not self.get_contact(contact_id):
            raise ValueError("unknown contact")
        now = time.time()
        jid = f"jb-{uuid.uuid4().hex[:10]}"
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO jobs(id,contact_id,title,status,due_at,notes,source,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (jid, contact_id, title[:300], "open", due_at, notes.strip()[:4000], source, now, now))
        return self.get_job(jid) or {}

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT j.*, c.name AS contact_name FROM jobs j LEFT JOIN contacts c ON c.id=j.contact_id WHERE j.id=?", (job_id,)).fetchone()
        return dict(r) if r else None

    def list_jobs(self, *, status: str | None = None, contact_id: str | None = None) -> list[dict[str, Any]]:
        where, args = [], []
        if status:
            where.append("j.status=?")
            args.append(status)
        if contact_id:
            where.append("j.contact_id=?")
            args.append(contact_id)
        q = "SELECT j.*, c.name AS contact_name FROM jobs j LEFT JOIN contacts c ON c.id=j.contact_id"
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY (j.due_at IS NULL), j.due_at, j.created_at"
        with self._lock, self._conn() as c:
            return [dict(r) for r in c.execute(q, args)]

    def update_job(self, job_id: str, **fields: Any) -> dict[str, Any] | None:
        sets = {k: v for k, v in fields.items() if k in _JOB_FIELDS and (v is not None or k in ("due_at", "contact_id"))}
        if "status" in sets and sets["status"] not in JOB_STATUSES:
            raise ValueError(f"status must be one of {JOB_STATUSES}")
        if "title" in sets and not str(sets["title"]).strip():
            raise ValueError("a job needs a title")
        if sets.get("contact_id") and not self.get_contact(sets["contact_id"]):
            raise ValueError("unknown contact")
        now = time.time()
        if sets:
            if "status" in sets:
                sets["done_at"] = now if sets["status"] == "done" else None
            cols = ", ".join(f"{k}=?" for k in sets)
            with self._lock, self._conn() as c:
                c.execute(f"UPDATE jobs SET {cols}, updated_at=? WHERE id=?", [*sets.values(), now, job_id])
        return self.get_job(job_id)

    def delete_job(self, job_id: str) -> bool:
        with self._lock, self._conn() as c:
            n = c.execute("DELETE FROM jobs WHERE id=?", (job_id,)).rowcount
            c.execute("UPDATE reminders SET job_id=NULL WHERE job_id=?", (job_id,))
        return n > 0

    # -- reminders --------------------------------------------------------------------------------------------
    def add_reminder(self, text: str, *, due_at: float | None = None, contact_id: str | None = None, job_id: str | None = None, source: str = "manual") -> dict[str, Any]:
        text = (text or "").strip()
        if not text:
            raise ValueError("a reminder needs text")
        rid = f"rm-{uuid.uuid4().hex[:10]}"
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO reminders(id,contact_id,job_id,text,due_at,source,created_at) VALUES(?,?,?,?,?,?,?)",
                      (rid, contact_id, job_id, text[:500], due_at, source, time.time()))
        return self.get_reminder(rid) or {}

    def get_reminder(self, reminder_id: str) -> dict[str, Any] | None:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM reminders WHERE id=?", (reminder_id,)).fetchone()
        return self._rem(r) if r else None

    @staticmethod
    def _rem(r: sqlite3.Row) -> dict[str, Any]:
        d = dict(r)
        d["done"] = bool(d["done"])
        return d

    def list_reminders(self, *, include_done: bool = False) -> list[dict[str, Any]]:
        q = "SELECT * FROM reminders" + ("" if include_done else " WHERE done=0") + " ORDER BY (due_at IS NULL), due_at, created_at"
        with self._lock, self._conn() as c:
            return [self._rem(r) for r in c.execute(q)]

    def complete_reminder(self, reminder_id: str, done: bool = True) -> dict[str, Any] | None:
        with self._lock, self._conn() as c:
            c.execute("UPDATE reminders SET done=?, done_at=? WHERE id=?", (1 if done else 0, time.time() if done else None, reminder_id))
        return self.get_reminder(reminder_id)

    def delete_reminder(self, reminder_id: str) -> bool:
        with self._lock, self._conn() as c:
            return c.execute("DELETE FROM reminders WHERE id=?", (reminder_id,)).rowcount > 0


class _Conn:
    """sqlite3 connection that commits and CLOSES on exit (a bare `with conn` only commits)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._c = conn

    def __enter__(self) -> sqlite3.Connection:
        return self._c

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self._c.commit()
            else:
                self._c.rollback()
        finally:
            self._c.close()


def life_store_for(workspace: Any) -> LifeStore:
    def factory() -> LifeStore:
        return LifeStore(Path(workspace.conversations_db_path).parent / "life.db")

    getter = getattr(workspace, "_get_or_create", None)
    return getter("life_store", factory) if getter else factory()
