from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from typing import Any

from aether.memory.base import BaseMemoryStore, MemoryDocument


class SemanticMemory(BaseMemoryStore):
    """
    Local-first Semantic Memory store using SQLite.
    Provides simple keyword-matching document retrieval.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._lock = threading.Lock()
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

        query_words = set(query.lower().split())
        if not query_words:
            return []

        scored_docs: list[tuple[float, MemoryDocument]] = []

        with self._lock:
            cursor = self._conn.execute("SELECT id, content, metadata, timestamp FROM documents")
            rows = cursor.fetchall()

        for row in rows:
            doc_id, content, meta_str, ts_str = row
            content_lower = content.lower()


            # Simple word-level overlap
            match_count = sum(1 for w in query_words if w in content_lower)

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


