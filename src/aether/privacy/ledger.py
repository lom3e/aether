"""
The egress ledger: one local row per call that may send data to a model provider. It stores WHAT KIND of data left and
how much, never the content itself, so the ledger cannot become a second copy of the user's data.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS egress (
    id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    workspace_id TEXT,
    session_id TEXT,
    provider TEXT NOT NULL,
    model TEXT,
    local INTEGER NOT NULL DEFAULT 0,
    purpose TEXT,
    messages INTEGER NOT NULL DEFAULT 0,
    chars INTEGER NOT NULL DEFAULT 0,
    images INTEGER NOT NULL DEFAULT 0,
    image_bytes INTEGER NOT NULL DEFAULT 0,
    redactions TEXT NOT NULL DEFAULT '{}',
    unmasked INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ok',
    error_kind TEXT
);
CREATE INDEX IF NOT EXISTS idx_egress_ts ON egress(ts DESC);
CREATE TABLE IF NOT EXISTS privacy_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

DEFAULT_SETTINGS = {"redact": True}


class EgressLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # -- settings ------------------------------------------------------------------------------------------
    def settings(self) -> dict[str, Any]:
        out = dict(DEFAULT_SETTINGS)
        with self._lock, self._conn() as c:
            for row in c.execute("SELECT key, value FROM privacy_settings"):
                try:
                    out[row["key"]] = json.loads(row["value"])
                except (TypeError, ValueError):
                    pass
        return out

    def update_settings(self, **values: Any) -> dict[str, Any]:
        allowed = set(DEFAULT_SETTINGS)
        with self._lock, self._conn() as c:
            for k, v in values.items():
                if k in allowed:
                    c.execute("INSERT INTO privacy_settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, json.dumps(v)))
        return self.settings()

    # -- entries -------------------------------------------------------------------------------------------
    def record(
        self, *, provider: str, model: str | None, local: bool, workspace_id: str | None = None, session_id: str | None = None,
        purpose: str | None = None, messages: int = 0, chars: int = 0, images: int = 0, image_bytes: int = 0,
        redactions: dict[str, int] | None = None, unmasked: bool = False, status: str = "ok", error_kind: str | None = None,
    ) -> dict[str, Any]:
        entry_id = f"eg-{uuid.uuid4().hex[:12]}"
        row = (entry_id, time.time(), workspace_id, session_id, provider, model, 1 if local else 0, purpose, messages, chars, images,
               image_bytes, json.dumps(redactions or {}), 1 if unmasked else 0, status, error_kind)
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO egress VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
        return self.get(entry_id) or {}

    @staticmethod
    def _row(r: sqlite3.Row) -> dict[str, Any]:
        d = dict(r)
        d["local"] = bool(d["local"])
        d["unmasked"] = bool(d["unmasked"])
        d["redactions"] = json.loads(d.get("redactions") or "{}")
        return d

    def get(self, entry_id: str) -> dict[str, Any] | None:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM egress WHERE id=?", (entry_id,)).fetchone()
        return self._row(r) if r else None

    def list(self, limit: int = 100, since: float | None = None, session_id: str | None = None) -> list[dict[str, Any]]:
        q, args = "SELECT * FROM egress", []
        where = []
        if since is not None:
            where.append("ts >= ?")
            args.append(since)
        if session_id:
            where.append("session_id = ?")
            args.append(session_id)
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY ts DESC LIMIT ?"
        args.append(max(1, min(int(limit), 1000)))
        with self._lock, self._conn() as c:
            return [self._row(r) for r in c.execute(q, args)]

    def summary(self, since: float | None = None) -> dict[str, Any]:
        rows = self.list(limit=1000, since=since)
        cloud = [r for r in rows if not r["local"]]
        red: dict[str, int] = {}
        for r in cloud:
            for k, v in r["redactions"].items():
                red[k] = red.get(k, 0) + v
        return {
            "requests": len(rows),
            "cloud_requests": len(cloud),
            "local_requests": len(rows) - len(cloud),
            "images_sent": sum(r["images"] for r in cloud),
            "redactions": red,
            "redactions_total": sum(red.values()),
            "providers": sorted({r["provider"] for r in cloud}),
        }
