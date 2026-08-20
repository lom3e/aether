from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from typing import Any

from aether.memory.base import BaseMemoryStore, MemoryDocument
from aether.core.paths import get_default_memory_db_path
from aether.core.sqlite import get_sqlite_connection


class SemanticMemory(BaseMemoryStore):
    """
    Local-first Semantic Memory store using SQLite.
    Provides simple keyword-matching document retrieval.
    """

    def __init__(self, db_path: str | None = None) -> None:
        using_default_path = db_path is None
        if db_path is None:
            resolved = get_default_memory_db_path()
            resolved.parent.mkdir(parents=True, exist_ok=True)
            db_path = str(resolved)

        self.db_path = db_path
        self._conn = get_sqlite_connection(self.db_path, check_same_thread=False)
        self._lock = threading.Lock()
        try:
            self._init_db()
            # A read-only SQLite file can still allow CREATE IF NOT EXISTS.
            # Probe a real write so failures happen during initialization.
            with self._conn:
                self._conn.execute("CREATE TABLE IF NOT EXISTS _aether_write_probe (id INTEGER PRIMARY KEY)")
                self._conn.execute("INSERT INTO _aether_write_probe DEFAULT VALUES")
                self._conn.execute("DELETE FROM _aether_write_probe")
        except sqlite3.OperationalError:
            self._conn.close()
            if not using_default_path:
                raise
            # The global default is a convenience. A locked-down installation
            # must still be able to run; explicit db paths remain strict.
            self.db_path = ":memory:"
            self._conn = get_sqlite_connection(self.db_path, check_same_thread=False)
            self._init_db()

    def _init_db(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                metadata TEXT,
                timestamp TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def add(self, document: MemoryDocument) -> None:
        """
        Store a MemoryDocument in the database.
        """
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO documents (id, content, metadata, timestamp) VALUES (?, ?, ?, ?)",
                (
                    document.id,
                    document.content,
                    json.dumps(document.metadata),
                    document.timestamp.isoformat(),
                ),
            )
            self._conn.commit()


    def search(self, query: str, limit: int = 5) -> list[MemoryDocument]:
        """
        Search documents by keyword overlap.
        Returns up to `limit` documents ordered by similarity score.
        """
        if not query:
            return []

        import re
        tokens = [w.lower() for w in re.findall(r"\w+", query)]
        query_words = {w for w in tokens if len(w) > 2} or set(tokens)
        if not query_words:
            return []

        scored_docs: list[tuple[float, MemoryDocument]] = []

        with self._lock:
            cursor = self._conn.execute("SELECT id, content, metadata, timestamp FROM documents")
            rows = cursor.fetchall()

        for row in rows:
            doc_id, content, meta_str, ts_str = row
            content_words = set(re.findall(r"\w+", content.lower()))

            # Token/stem-level overlap (avoid single/two letter noise)
            match_count = sum(
                1 for w in query_words
                if any(w == cw or (len(w) >= 3 and len(cw) >= 3 and (w in cw or cw in w)) for cw in content_words)
            )

            if match_count > 0:
                doc = MemoryDocument(
                    content=content,
                    id=doc_id,
                    metadata=json.loads(meta_str) if meta_str else {},
                    timestamp=datetime.fromisoformat(ts_str),
                )
                scored_docs.append((match_count, doc))

        # Sort by score descending, then by timestamp descending
        scored_docs.sort(key=lambda x: (x[0], x[1].timestamp.timestamp()), reverse=True)

        return [doc for _, doc in scored_docs[:limit]]

    def clear(self) -> None:
        """
        Clear all documents in semantic memory.
        """
        with self._lock:
            self._conn.execute("DELETE FROM documents")
            self._conn.commit()


    def close(self) -> None:
        """
        Close the SQLite database connection.
        """
        self._conn.close()

    def __del__(self) -> None:
        """
        Ensure SQLite database connection is closed when object is deleted.
        """
        try:
            self.close()
        except Exception:
            pass

    def __enter__(self) -> SemanticMemory:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
