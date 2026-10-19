"""
"Remember this screen": one capture the user explicitly chose to keep, stored as a short text description in the local
knowledge store with an expiry date. The image itself is never stored. Nothing here captures anything: it only receives
the description of an image the user already previewed and confirmed.
"""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

ALLOWED_TTL_DAYS = (7, 30)
SOURCE_PREFIX = "screen:"
MAX_DESCRIPTION_CHARS = 1500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS screen_memories (
    id TEXT PRIMARY KEY,
    workspace_id TEXT,
    source TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    chars INTEGER NOT NULL DEFAULT 0,
    provider TEXT,
    model TEXT
);
"""


class ScreenMemory:
    def __init__(self, path: str | Path, knowledge: Any) -> None:
        self.path = str(path)
        self.knowledge = knowledge
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return _Conn(conn)

    @staticmethod
    def _row(r: sqlite3.Row) -> dict[str, Any]:
        return dict(r)

    def remember(self, description: str, *, ttl_days: int = 7, title: str = "", workspace_id: str | None = None,
                 provider: str = "", model: str = "") -> dict[str, Any]:
        text = (description or "").strip()[:MAX_DESCRIPTION_CHARS]
        if not text:
            raise ValueError("empty description")
        if ttl_days not in ALLOWED_TTL_DAYS:
            raise ValueError(f"ttl_days must be one of {ALLOWED_TTL_DAYS}")
        mem_id = f"scr-{uuid.uuid4().hex[:10]}"
        source = f"{SOURCE_PREFIX}{mem_id}"
        now = time.time()
        label = (title or text.split("\n")[0])[:80]
        from aether.knowledge.chunk import KnowledgeChunk

        self.knowledge.add(KnowledgeChunk(
            content=f"[Screen memory, {time.strftime('%Y-%m-%d %H:%M', time.localtime(now))}] {label}\n{text}",
            source=source, chunk_index=0, metadata={"kind": "screen_memory", "memory_id": mem_id},
        ))
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO screen_memories VALUES (?,?,?,?,?,?,?,?,?)",
                      (mem_id, workspace_id, source, label, now, now + ttl_days * 86400, len(text), provider, model))
        return self.get(mem_id) or {}

    def get(self, mem_id: str) -> dict[str, Any] | None:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM screen_memories WHERE id=?", (mem_id,)).fetchone()
        return self._row(r) if r else None

    def list(self) -> list[dict[str, Any]]:
        self.sweep()
        with self._lock, self._conn() as c:
            return [self._row(r) for r in c.execute("SELECT * FROM screen_memories ORDER BY created_at DESC")]

    def forget(self, mem_id: str) -> dict[str, Any]:
        """Deletes the memory and VERIFIES the knowledge chunks are really gone."""
        row = self.get(mem_id)
        if row is None:
            return {"forgotten": False, "reason": "not_found"}
        self.knowledge.remove_source(row["source"])
        gone = not self.knowledge.get_by_source(row["source"])
        if gone:
            with self._lock, self._conn() as c:
                c.execute("DELETE FROM screen_memories WHERE id=?", (mem_id,))
        return {"forgotten": gone, "verified_gone": gone, "id": mem_id}

    def sweep(self) -> int:
        """Removes expired memories (text and record). Called whenever the list or the chat is touched."""
        with self._lock, self._conn() as c:
            expired = [self._row(r) for r in c.execute("SELECT * FROM screen_memories WHERE expires_at < ?", (time.time(),))]
        removed = 0
        for row in expired:
            self.knowledge.remove_source(row["source"])
            if not self.knowledge.get_by_source(row["source"]):
                with self._lock, self._conn() as c:
                    c.execute("DELETE FROM screen_memories WHERE id=?", (row["id"],))
                removed += 1
        return removed


class _Conn:
    """sqlite3 connection that commits and closes with the with-block."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._c = conn

    def __enter__(self) -> sqlite3.Connection:
        return self._c

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self._c.commit()
        finally:
            self._c.close()


def screen_memory_for(workspace: Any) -> ScreenMemory:
    def factory() -> ScreenMemory:
        return ScreenMemory(Path(workspace.conversations_db_path).parent / "screen_memory.db", workspace.knowledge)

    getter = getattr(workspace, "_get_or_create", None)
    return getter("screen_memory", factory) if getter else factory()
