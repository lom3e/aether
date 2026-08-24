"""
KnowledgeStore — SQLite-backed document knowledge base with multi-scope support (Phase 12 / P1-04).

Stores :class:`~aether.knowledge.chunk.KnowledgeChunk` objects and
provides keyword-based retrieval across 'workspace', 'project', and 'system' scopes.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from aether.core.paths import get_default_knowledge_db_path
from aether.core.sqlite import get_sqlite_connection
from aether.knowledge.chunk import KnowledgeChunk, KnowledgeScope


class KnowledgeStore:
    """
    Local-first knowledge store backed by SQLite with multi-scope support.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file. Defaults to the configured Aether
        data directory knowledge.db. Pass ``:memory:`` for an ephemeral
        in-memory store (useful for testing).
    """

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            resolved = get_default_knowledge_db_path()
            resolved.parent.mkdir(parents=True, exist_ok=True)
            db_path = str(resolved)

        self._db_path = db_path
        self._conn = get_sqlite_connection(db_path, check_same_thread=False)
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
                    scope       TEXT NOT NULL DEFAULT 'workspace',
                    project_id  TEXT DEFAULT NULL
                )
                """
            )

            # Track documents for UI and API
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
                    scope TEXT NOT NULL DEFAULT 'workspace',
                    project_id TEXT DEFAULT NULL
                )
                """
            )

            # Schema migrations for existing databases
            doc_cols = {
                row[1]
                for row in self._conn.execute("PRAGMA table_info(documents)").fetchall()
            }
            if "content_hash" not in doc_cols:
                self._conn.execute("ALTER TABLE documents ADD COLUMN content_hash TEXT")
            if "scope" not in doc_cols:
                self._conn.execute("ALTER TABLE documents ADD COLUMN scope TEXT DEFAULT 'workspace'")
            if "project_id" not in doc_cols:
                self._conn.execute("ALTER TABLE documents ADD COLUMN project_id TEXT DEFAULT NULL")

            kc_cols = {
                row[1]
                for row in self._conn.execute("PRAGMA table_info(knowledge_chunks)").fetchall()
            }
            if "scope" not in kc_cols:
                self._conn.execute("ALTER TABLE knowledge_chunks ADD COLUMN scope TEXT DEFAULT 'workspace'")
            if "project_id" not in kc_cols:
                self._conn.execute("ALTER TABLE knowledge_chunks ADD COLUMN project_id TEXT DEFAULT NULL")

            # Create indices after ensuring all columns exist
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_kc_source
                ON knowledge_chunks (source)
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_kc_scope
                ON knowledge_chunks (scope)
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_kc_project_id
                ON knowledge_chunks (project_id)
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_doc_scope
                ON documents (scope)
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_doc_project_id
                ON documents (project_id)
                """
            )

            self._conn.commit()

    # ------------------------------------------------------------------
    # Document Tracking
    # ------------------------------------------------------------------

    def register_document(
        self,
        doc_id: str,
        filename: str,
        size_bytes: int,
        content_hash: str | None = None,
        scope: str = KnowledgeScope.WORKSPACE.value,
        project_id: str | None = None,
    ) -> None:
        clean_scope = KnowledgeScope.normalize(scope)
        clean_pid = str(project_id).strip() if project_id and str(project_id).strip() else None
        if clean_scope != KnowledgeScope.PROJECT.value:
            clean_pid = None

        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO documents
                    (id, filename, size_bytes, content_hash, chunk_count, status, uploaded_at, scope, project_id)
                VALUES (?, ?, ?, ?, 0, 'processing', ?, ?, ?)
                """,
                (doc_id, filename, size_bytes, content_hash, datetime.now().isoformat(), clean_scope, clean_pid),
            )
            self._conn.commit()

    def update_document(self, doc_id: str, status: str, chunk_count: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE documents SET status = ?, chunk_count = ? WHERE id = ?",
                (status, chunk_count, doc_id),
            )
            self._conn.commit()

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, filename, size_bytes, content_hash, chunk_count, status, uploaded_at, scope, project_id "
                "FROM documents WHERE id = ?",
                (doc_id,),
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
            "scope": row[7] or KnowledgeScope.WORKSPACE.value,
            "project_id": row[8],
        }

    def list_documents(
        self,
        scope: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            conditions: list[str] = []
            params: list[Any] = []

            if scope:
                clean_scope = KnowledgeScope.normalize(scope)
                conditions.append("scope = ?")
                params.append(clean_scope)

            if project_id is not None:
                clean_pid = str(project_id).strip()
                if clean_pid in ("", "none", "unassigned"):
                    conditions.append("(project_id IS NULL OR project_id = '')")
                else:
                    conditions.append("project_id = ?")
                    params.append(clean_pid)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            query = (
                f"SELECT id, filename, size_bytes, content_hash, chunk_count, status, uploaded_at, scope, project_id "
                f"FROM documents {where_clause} ORDER BY uploaded_at DESC"
            )
            cursor = self._conn.execute(query, tuple(params))
            return [
                {
                    "id": row[0],
                    "filename": row[1],
                    "size_bytes": row[2],
                    "content_hash": row[3],
                    "chunk_count": row[4],
                    "status": row[5],
                    "uploaded_at": row[6],
                    "scope": row[7] or KnowledgeScope.WORKSPACE.value,
                    "project_id": row[8],
                }
                for row in cursor.fetchall()
            ]

    def find_document_by_hash(
        self,
        content_hash: str,
        scope: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Return the document with *content_hash*, respecting scope and project isolation."""
        with self._lock:
            conditions = ["content_hash = ?"]
            params: list[Any] = [content_hash]

            if scope:
                conditions.append("scope = ?")
                params.append(KnowledgeScope.normalize(scope))

            if project_id is not None:
                clean_pid = str(project_id).strip()
                if clean_pid:
                    conditions.append("project_id = ?")
                    params.append(clean_pid)
                else:
                    conditions.append("(project_id IS NULL OR project_id = '')")

            query = (
                f"SELECT id, filename, size_bytes, content_hash, chunk_count, status, uploaded_at, scope, project_id "
                f"FROM documents WHERE {' AND '.join(conditions)} LIMIT 1"
            )
            row = self._conn.execute(query, tuple(params)).fetchone()

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
            "scope": row[7] or KnowledgeScope.WORKSPACE.value,
            "project_id": row[8],
        }

    def delete_document(self, doc_id: str, allow_system: bool = False) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT filename, scope FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
            if row and row[1] == KnowledgeScope.SYSTEM.value and not allow_system:
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
    # Write Chunks
    # ------------------------------------------------------------------

    def add(self, chunk: KnowledgeChunk) -> None:
        """Store a single :class:`KnowledgeChunk`."""
        clean_scope = KnowledgeScope.normalize(chunk.scope)
        clean_pid = str(chunk.project_id).strip() if chunk.project_id and str(chunk.project_id).strip() else None
        if clean_scope != KnowledgeScope.PROJECT.value:
            clean_pid = None

        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO knowledge_chunks
                    (id, content, source, chunk_index, metadata, created_at, scope, project_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.id,
                    chunk.content,
                    chunk.source,
                    chunk.chunk_index,
                    json.dumps(chunk.metadata) if chunk.metadata else "{}",
                    chunk.created_at.isoformat(),
                    clean_scope,
                    clean_pid,
                ),
            )
            self._conn.commit()

    def add_many(self, chunks: list[KnowledgeChunk]) -> None:
        """Store multiple chunks in a single transaction."""
        data = []
        for c in chunks:
            clean_scope = KnowledgeScope.normalize(c.scope)
            clean_pid = str(c.project_id).strip() if c.project_id and str(c.project_id).strip() else None
            if clean_scope != KnowledgeScope.PROJECT.value:
                clean_pid = None
            data.append((
                c.id,
                c.content,
                c.source,
                c.chunk_index,
                json.dumps(c.metadata) if c.metadata else "{}",
                c.created_at.isoformat(),
                clean_scope,
                clean_pid,
            ))

        with self._lock:
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO knowledge_chunks
                    (id, content, source, chunk_index, metadata, created_at, scope, project_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                data,
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Read & Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        limit: int = 5,
        scope: str | None = None,
        project_id: str | None = None,
        include_workspace_fallback: bool = True,
    ) -> list[KnowledgeChunk]:
        """
        Search knowledge chunks by keyword overlap with scope & project semantics.

        Parameters
        ----------
        query:
            The search query string.
        limit:
            Maximum number of chunks to return.
        scope:
            Explicit scope ('workspace', 'project', or 'system').
        project_id:
            Target project ID. When supplied and include_workspace_fallback=True,
            matches chunks from the specified project plus workspace/system knowledge,
            while strictly excluding chunks from other projects.
        include_workspace_fallback:
            Whether to include workspace and system knowledge when project_id is provided.
        """
        if not query or not query.strip():
            return []

        tokens = [w.lower() for w in re.findall(r"\w+", query)]
        query_words = {w for w in tokens if len(w) > 2} or set(tokens)
        if not query_words:
            return []

        with self._lock:
            conditions: list[str] = []
            params: list[Any] = []

            if project_id:
                clean_pid = str(project_id).strip()
                if include_workspace_fallback:
                    conditions.append(
                        "((project_id = ? AND scope = 'project') OR scope IN ('workspace', 'system'))"
                    )
                    params.append(clean_pid)
                else:
                    conditions.append("project_id = ? AND scope = 'project'")
                    params.append(clean_pid)
            elif scope:
                clean_scope = KnowledgeScope.normalize(scope)
                conditions.append("scope = ?")
                params.append(clean_scope)
                if clean_scope == KnowledgeScope.WORKSPACE.value:
                    conditions.append("(project_id IS NULL OR project_id = '')")
            else:
                # Default: workspace + system (no foreign project chunks)
                conditions.append("(project_id IS NULL OR scope IN ('workspace', 'system'))")

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            cursor = self._conn.execute(
                f"SELECT id, content, source, chunk_index, metadata, created_at, scope, project_id "
                f"FROM knowledge_chunks {where_clause}",
                tuple(params),
            )
            rows = cursor.fetchall()

        scored: list[tuple[int, int, KnowledgeChunk]] = []
        for row in rows:
            chunk_id, content, source, chunk_index, meta_str, ts_str, chunk_scope, chunk_pid = row[0:8]
            content_words = set(re.findall(r"\w+", content.lower()))
            score = sum(
                1 for w in query_words
                if any(w == cw or (len(w) >= 3 and len(cw) >= 3 and (w in cw or cw in w)) for cw in content_words)
            )
            if score > 0:
                # Prioritize project-specific chunks slightly on equal scores (1 if project match, 0 otherwise)
                project_priority = 1 if (project_id and chunk_pid == project_id) else 0
                chunk = KnowledgeChunk(
                    content=content,
                    source=source,
                    chunk_index=chunk_index,
                    id=chunk_id,
                    metadata=json.loads(meta_str) if meta_str else {},
                    scope=chunk_scope or KnowledgeScope.WORKSPACE.value,
                    project_id=chunk_pid,
                    created_at=datetime.fromisoformat(ts_str),
                )
                scored.append((score, project_priority, chunk))

        # Sort by match score desc, then project priority desc, then chunk_index asc
        scored.sort(key=lambda x: (-x[0], -x[1], x[2].chunk_index))
        return [c for _, _, c in scored[:limit]]

    def list_sources(
        self,
        scope: str | None = None,
        project_id: str | None = None,
    ) -> list[str]:
        """Return a sorted list of all indexed source paths."""
        with self._lock:
            conditions: list[str] = []
            params: list[Any] = []

            if scope:
                conditions.append("scope = ?")
                params.append(KnowledgeScope.normalize(scope))

            if project_id is not None:
                clean_pid = str(project_id).strip()
                if clean_pid in ("", "none", "unassigned"):
                    conditions.append("(project_id IS NULL OR project_id = '')")
                else:
                    conditions.append("project_id = ?")
                    params.append(clean_pid)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            cursor = self._conn.execute(
                f"SELECT DISTINCT source FROM knowledge_chunks {where_clause} ORDER BY source",
                tuple(params),
            )
            return [row[0] for row in cursor.fetchall()]

    def count(
        self,
        scope: str | None = None,
        project_id: str | None = None,
    ) -> int:
        """Return the total number of stored chunks."""
        with self._lock:
            conditions: list[str] = []
            params: list[Any] = []

            if scope:
                conditions.append("scope = ?")
                params.append(KnowledgeScope.normalize(scope))

            if project_id is not None:
                clean_pid = str(project_id).strip()
                if clean_pid in ("", "none", "unassigned"):
                    conditions.append("(project_id IS NULL OR project_id = '')")
                else:
                    conditions.append("project_id = ?")
                    params.append(clean_pid)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            cursor = self._conn.execute(
                f"SELECT COUNT(*) FROM knowledge_chunks {where_clause}",
                tuple(params),
            )
            return cursor.fetchone()[0]

    def count_by_scope(self) -> dict[str, int]:
        """Return chunk counts grouped by scope."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT scope, COUNT(*) FROM knowledge_chunks GROUP BY scope"
            )
            counts = {row[0]: row[1] for row in cursor.fetchall()}
            for s in KnowledgeScope:
                counts.setdefault(s.value, 0)
            return counts

    def get_by_source(self, source: str) -> list[KnowledgeChunk]:
        """Retrieve all chunks from a specific source, ordered by chunk_index."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT id, content, source, chunk_index, metadata, created_at, scope, project_id "
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
                scope=row[6] or KnowledgeScope.WORKSPACE.value,
                project_id=row[7],
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Delete & Clear
    # ------------------------------------------------------------------

    def clear(
        self,
        scope: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """Remove all chunks from the store, optionally scoped to a project or scope."""
        with self._lock:
            conditions: list[str] = []
            params: list[Any] = []

            if scope:
                conditions.append("scope = ?")
                params.append(KnowledgeScope.normalize(scope))

            if project_id is not None:
                clean_pid = str(project_id).strip()
                if clean_pid:
                    conditions.append("project_id = ?")
                    params.append(clean_pid)
                else:
                    conditions.append("(project_id IS NULL OR project_id = '')")

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            self._conn.execute(f"DELETE FROM knowledge_chunks {where_clause}", tuple(params))
            self._conn.execute(f"DELETE FROM documents {where_clause}", tuple(params))
            self._conn.commit()

    def remove_source(self, source: str) -> int:
        """Remove all chunks associated with a specific source."""
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
