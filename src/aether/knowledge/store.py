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
                    created_at  TEXT NOT NULL,
                    scope       TEXT NOT NULL DEFAULT 'workspace'
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
            # Track documents for UI
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    content_hash TEXT,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'workspace'
                )
                """
            )
            # Schema migrations
            doc_cols = {
                row[1]
                for row in self._conn.execute("PRAGMA table_info(documents)").fetchall()
            }
            if "content_hash" not in doc_cols:
                self._conn.execute("ALTER TABLE documents ADD COLUMN content_hash TEXT")
            if "scope" not in doc_cols:
                self._conn.execute("ALTER TABLE documents ADD COLUMN scope TEXT DEFAULT 'workspace'")

            kc_cols = {
                row[1]
                for row in self._conn.execute("PRAGMA table_info(knowledge_chunks)").fetchall()
            }
            if "scope" not in kc_cols:
                self._conn.execute("ALTER TABLE knowledge_chunks ADD COLUMN scope TEXT DEFAULT 'workspace'")

            self._conn.commit()

    # ------------------------------------------------------------------
    # Document Tracking (UI)
    # ------------------------------------------------------------------

    def register_document(
        self,
        doc_id: str,
        filename: str,
        size_bytes: int,
        content_hash: str | None = None,
        scope: str = "workspace",
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO documents
                    (id, filename, size_bytes, content_hash, chunk_count, status, uploaded_at, scope)
                VALUES (?, ?, ?, ?, 0, 'processing', ?, ?)
                """,
                (doc_id, filename, size_bytes, content_hash, datetime.now().isoformat(), scope)
            )
            self._conn.commit()

    def update_document(self, doc_id: str, status: str, chunk_count: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE documents SET status = ?, chunk_count = ? WHERE id = ?",
                (status, chunk_count, doc_id)
            )
            self._conn.commit()

    def list_documents(self, scope: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if scope:
                cursor = self._conn.execute(
                    "SELECT id, filename, size_bytes, content_hash, chunk_count, status, uploaded_at, scope "
                    "FROM documents WHERE scope = ? ORDER BY uploaded_at DESC",
                    (scope,)
                )
            else:
                cursor = self._conn.execute(
                    "SELECT id, filename, size_bytes, content_hash, chunk_count, status, uploaded_at, scope "
                    "FROM documents ORDER BY uploaded_at DESC"
                )
            return [
                {
                    "id": row[0],
                    "filename": row[1],
                    "size_bytes": row[2],
                    "content_hash": row[3],
                    "chunk_count": row[4],
                    "status": row[5],
                    "uploaded_at": row[6],
                    "scope": row[7] if len(row) > 7 and row[7] else "workspace",
                }
                for row in cursor.fetchall()
            ]

    def find_document_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        """Return the document with *content_hash*, if one is indexed."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id, filename, size_bytes, content_hash, chunk_count, status, uploaded_at, scope "
                "FROM documents WHERE content_hash = ? LIMIT 1",
                (content_hash,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "filename": row[1],
            "size_bytes": row[2],
            "content_hash": row[3],
            "chunk_count": row[4],
            "status": row[5],
            "uploaded_at": row[6],
            "scope": row[7] if len(row) > 7 and row[7] else "workspace",
        }

    def delete_document(self, doc_id: str, allow_system: bool = False) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT filename, scope FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
            if row and row[1] == "system" and not allow_system:
                raise ValueError("System knowledge documents cannot be deleted.")

            self._conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            self._conn.execute("DELETE FROM knowledge_chunks WHERE source = ?", (doc_id,))
            if row:
                self._conn.execute(
                    "DELETE FROM knowledge_chunks WHERE source = ? OR source LIKE ?",
                    (row[0], f"%_{row[0]}"),
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
                    (id, content, source, chunk_index, metadata, created_at, scope)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.id,
                    chunk.content,
                    chunk.source,
                    chunk.chunk_index,
                    json.dumps(chunk.metadata) if chunk.metadata else "{}",
                    chunk.created_at.isoformat(),
                    chunk.scope or "workspace",
                ),
            )
            self._conn.commit()

    def add_many(self, chunks: list[KnowledgeChunk]) -> None:
        """Store multiple chunks in a single transaction."""
        with self._lock:
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO knowledge_chunks
                    (id, content, source, chunk_index, metadata, created_at, scope)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c.id,
                        c.content,
                        c.source,
                        c.chunk_index,
                        json.dumps(c.metadata) if c.metadata else "{}",
                        c.created_at.isoformat(),
                        c.scope or "workspace",
                    )
                    for c in chunks
                ],
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search(self, query: str, limit: int = 5, scope: str | None = None) -> list[KnowledgeChunk]:
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
        scope:
            Optional scope filter ('workspace' or 'system'). None searches all.
        """
        if not query or not query.strip():
            return []

        import re
        tokens = [w.lower() for w in re.findall(r"\w+", query)]
        query_words = {w for w in tokens if len(w) > 2} or set(tokens)
        if not query_words:
            return []

        with self._lock:
            if scope:
                cursor = self._conn.execute(
                    "SELECT id, content, source, chunk_index, metadata, created_at, scope "
                    "FROM knowledge_chunks WHERE scope = ?",
                    (scope,)
                )
            else:
                cursor = self._conn.execute(
                    "SELECT id, content, source, chunk_index, metadata, created_at, scope "
                    "FROM knowledge_chunks"
                )
            rows = cursor.fetchall()

        scored: list[tuple[int, KnowledgeChunk]] = []
        for row in rows:
            chunk_id, content, source, chunk_index, meta_str, ts_str = row[0:6]
            chunk_scope = row[6] if len(row) > 6 and row[6] else "workspace"
            content_words = set(re.findall(r"\w+", content.lower()))
            score = sum(
                1 for w in query_words
                if any(w == cw or (len(w) >= 3 and len(cw) >= 3 and (w in cw or cw in w)) for cw in content_words)
            )
            if score > 0:
                chunk = KnowledgeChunk(
                    content=content,
                    source=source,
                    chunk_index=chunk_index,
                    id=chunk_id,
                    metadata=json.loads(meta_str) if meta_str else {},
                    scope=chunk_scope,
                    created_at=datetime.fromisoformat(ts_str),
                )
                scored.append((score, chunk))

        # Sort by score desc, then chunk_index asc (document order for ties)
        scored.sort(key=lambda x: (-x[0], x[1].chunk_index))
        return [c for _, c in scored[:limit]]

    def list_sources(self, scope: str | None = None) -> list[str]:
        """Return a sorted list of all indexed source paths."""
        with self._lock:
            if scope:
                cursor = self._conn.execute(
                    "SELECT DISTINCT source FROM knowledge_chunks WHERE scope = ? ORDER BY source",
                    (scope,)
                )
            else:
                cursor = self._conn.execute(
                    "SELECT DISTINCT source FROM knowledge_chunks ORDER BY source"
                )
            return [row[0] for row in cursor.fetchall()]

    def count(self, scope: str | None = None) -> int:
        """Return the total number of stored chunks."""
        with self._lock:
            if scope:
                cursor = self._conn.execute(
                    "SELECT COUNT(*) FROM knowledge_chunks WHERE scope = ?",
                    (scope,)
                )
            else:
                cursor = self._conn.execute("SELECT COUNT(*) FROM knowledge_chunks")
            return cursor.fetchone()[0]

    def get_by_source(self, source: str) -> list[KnowledgeChunk]:
        """Retrieve all chunks from a specific source, ordered by chunk_index."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT id, content, source, chunk_index, metadata, created_at, scope "
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
                scope=row[6] if len(row) > 6 and row[6] else "workspace",
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def clear(self, scope: str | None = None) -> None:
        """Remove all chunks from the store, optionally scoped."""
        with self._lock:
            if scope:
                self._conn.execute("DELETE FROM knowledge_chunks WHERE scope = ?", (scope,))
                self._conn.execute("DELETE FROM documents WHERE scope = ?", (scope,))
            else:
                self._conn.execute("DELETE FROM knowledge_chunks")
                self._conn.execute("DELETE FROM documents")
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
