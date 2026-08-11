"""
KnowledgeStore — SQLite-backed document knowledge base.

Stores :class:`~aether.knowledge.chunk.KnowledgeChunk` objects and
provides keyword-based retrieval. The store is intentionally simple:
no embeddings, no external dependencies.

The public API is designed so that the storage backend (SQLite + keyword)
can be swapped for a vector database later without breaking callers.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from aether.knowledge.chunk import KnowledgeChunk


_DEFAULT_DB_PATH = "~/.aether/knowledge.db"


class KnowledgeStore:
    """
    Local-first knowledge store backed by SQLite.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file. Defaults to
        ``~/.aether/knowledge.db``. Pass ``:memory:`` for an ephemeral
        in-memory store (useful for testing).
    """

    def __init__(self, db_path: str | None = None) -> None:
        import os

        if db_path is None:
            resolved = Path(os.path.expanduser(_DEFAULT_DB_PATH))
            resolved.parent.mkdir(parents=True, exist_ok=True)
            db_path = str(resolved)

        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._init_db()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id          TEXT PRIMARY KEY,
                    content     TEXT NOT NULL,
                    source      TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL DEFAULT 0,
                    metadata    TEXT,
                    created_at  TEXT NOT NULL
                )
                """
            )
            # Index on source to speed up source-based queries
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_kc_source
                ON knowledge_chunks (source)
                """
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add(self, chunk: KnowledgeChunk) -> None:
        """Store a single :class:`KnowledgeChunk`."""
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO knowledge_chunks
                    (id, content, source, chunk_index, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.id,
                    chunk.content,
                    chunk.source,
                    chunk.chunk_index,
                    json.dumps(chunk.metadata) if chunk.metadata else "{}",
                    chunk.created_at.isoformat(),
                ),
            )
            self._conn.commit()

    def add_many(self, chunks: list[KnowledgeChunk]) -> None:
        """Store multiple chunks in a single transaction."""
        with self._lock:
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO knowledge_chunks
                    (id, content, source, chunk_index, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c.id,
                        c.content,
                        c.source,
                        c.chunk_index,
                        json.dumps(c.metadata) if c.metadata else "{}",
                        c.created_at.isoformat(),
                    )
                    for c in chunks
                ],
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search(self, query: str, limit: int = 5) -> list[KnowledgeChunk]:
        """
        Search knowledge chunks by keyword overlap.

        Returns up to *limit* chunks ordered by descending match score,
        then by chunk_index (document order) for equal scores.

        Parameters
        ----------
        query:
            The search query string.
        limit:
            Maximum number of chunks to return.
        """
        if not query or not query.strip():
            return []

        query_words = set(query.lower().split())
        if not query_words:
            return []

        with self._lock:
            cursor = self._conn.execute(
                "SELECT id, content, source, chunk_index, metadata, created_at "
                "FROM knowledge_chunks"
            )
            rows = cursor.fetchall()

        scored: list[tuple[int, KnowledgeChunk]] = []
        for row in rows:
            chunk_id, content, source, chunk_index, meta_str, ts_str = row
            content_lower = content.lower()
            score = sum(1 for w in query_words if w in content_lower)
            if score > 0:
                chunk = KnowledgeChunk(
                    content=content,
                    source=source,
                    chunk_index=chunk_index,
                    id=chunk_id,
                    metadata=json.loads(meta_str) if meta_str else {},
                    created_at=datetime.fromisoformat(ts_str),
                )
                scored.append((score, chunk))

        # Sort by score desc, then chunk_index asc (document order for ties)
        scored.sort(key=lambda x: (-x[0], x[1].chunk_index))
        return [c for _, c in scored[:limit]]

    def list_sources(self) -> list[str]:
        """Return a sorted list of all indexed source paths."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT DISTINCT source FROM knowledge_chunks ORDER BY source"
            )
            return [row[0] for row in cursor.fetchall()]

    def count(self) -> int:
        """Return the total number of stored chunks."""
        with self._lock:
            cursor = self._conn.execute("SELECT COUNT(*) FROM knowledge_chunks")
            return cursor.fetchone()[0]

    def get_by_source(self, source: str) -> list[KnowledgeChunk]:
        """Retrieve all chunks from a specific source, ordered by chunk_index."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT id, content, source, chunk_index, metadata, created_at "
                "FROM knowledge_chunks WHERE source = ? ORDER BY chunk_index",
                (source,),
            )
            rows = cursor.fetchall()

        return [
            KnowledgeChunk(
                content=row[1],
                source=row[2],
                chunk_index=row[3],
                id=row[0],
                metadata=json.loads(row[4]) if row[4] else {},
                created_at=datetime.fromisoformat(row[5]),
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Remove all chunks from the store."""
        with self._lock:
            self._conn.execute("DELETE FROM knowledge_chunks")
            self._conn.commit()

    def remove_source(self, source: str) -> int:
        """
        Remove all chunks associated with a specific source.

        Returns the number of chunks removed.
        """
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM knowledge_chunks WHERE source = ?", (source,)
            )
            self._conn.commit()
            return cursor.rowcount

    # ------------------------------------------------------------------
    # Context manager + cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the SQLite connection."""
        try:
            self._conn.close()
        except Exception:
            pass

    def __del__(self) -> None:
        self.close()

    def __enter__(self) -> KnowledgeStore:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"KnowledgeStore(db={self._db_path!r}, chunks={self.count()})"
