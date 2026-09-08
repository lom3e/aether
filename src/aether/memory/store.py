"""
Persistent SQLite storage adapter for Workforce Intelligence & Compounding Memory (Phase B).
Provides local-first ACID storage, multi-scope indexing, provenance retention, and deterministic retrieval.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Generator
import uuid

from aether.core.sqlite import get_sqlite_connection, sqlite_connection
from aether.memory.models import MemoryCategory, MemoryProvenance, WorkforceMemory
from aether.memory.sanitization import sanitize_memory_data, sanitize_memory_text


class WorkforceMemoryStore:
    """
    Persistent SQLite store for Workforce Memories.
    Scoped by workspace with optional workforce, agent, and mission dimensions.
    """

    def __init__(self, db_path: str | Path, default_workspace_id: str = "default") -> None:
        self.db_path = str(db_path)
        self.default_workspace_id = default_workspace_id
        self._is_memory = self.db_path == ":memory:" or "mode=memory" in self.db_path
        if self.db_path == ":memory:":
            self.db_path = f"file:memdb_memory_{uuid.uuid4().hex}?mode=memory&cache=shared"
        self._keepalive_conn: sqlite3.Connection | None = (
            get_sqlite_connection(self.db_path) if self._is_memory else None
        )
        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        with sqlite_connection(self.db_path) as conn:
            yield conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workforce_memories (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    team_name TEXT,
                    agent_name TEXT,
                    mission_id TEXT,
                    execution_id TEXT,
                    category TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    content TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    tags TEXT NOT NULL DEFAULT '[]',
                    is_archived INTEGER NOT NULL DEFAULT 0,
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_ws ON workforce_memories(workspace_id, is_deleted, is_archived)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_cat ON workforce_memories(category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_agent ON workforce_memories(agent_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_mission ON workforce_memories(mission_id, execution_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_created ON workforce_memories(created_at DESC)")
            conn.commit()

    # ------------------------------------------------------------------
    # CRUD Operations
    # ------------------------------------------------------------------

    def create_memory(self, memory: WorkforceMemory) -> WorkforceMemory:
        """
        Persists a new WorkforceMemory after applying strict privacy sanitization.
        """
        # Strict sanitization at persistence boundary
        clean_content = sanitize_memory_text(memory.content)
        clean_summary = sanitize_memory_text(memory.summary)
        clean_prov = sanitize_memory_data(memory.provenance.to_dict())
        prov_obj = MemoryProvenance.from_dict(clean_prov)

        sanitized_mem = WorkforceMemory(
            id=memory.id or f"mem_{uuid.uuid4().hex[:12]}",
            workspace_id=memory.workspace_id or self.default_workspace_id,
            category=memory.category,
            summary=clean_summary,
            content=clean_content,
            provenance=prov_obj,
            team_name=memory.team_name,
            agent_name=memory.agent_name,
            mission_id=memory.mission_id,
            execution_id=memory.execution_id,
            confidence=max(0.0, min(1.0, float(memory.confidence))),
            tags=[sanitize_memory_text(t) for t in memory.tags],
            is_archived=memory.is_archived,
            is_deleted=False,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
        )

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO workforce_memories (
                    id, workspace_id, team_name, agent_name, mission_id, execution_id,
                    category, summary, content, provenance, confidence, tags,
                    is_archived, is_deleted, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sanitized_mem.id,
                    sanitized_mem.workspace_id,
                    sanitized_mem.team_name,
                    sanitized_mem.agent_name,
                    sanitized_mem.mission_id,
                    sanitized_mem.execution_id,
                    sanitized_mem.category.value if isinstance(sanitized_mem.category, MemoryCategory) else str(sanitized_mem.category),
                    sanitized_mem.summary,
                    sanitized_mem.content,
                    json.dumps(sanitized_mem.provenance.to_dict()),
                    sanitized_mem.confidence,
                    json.dumps(sanitized_mem.tags),
                    1 if sanitized_mem.is_archived else 0,
                    0,
                    sanitized_mem.created_at,
                    sanitized_mem.updated_at,
                ),
            )
            conn.commit()

        return sanitized_mem

    def get_memory(self, memory_id: str, workspace_id: str | None = None) -> WorkforceMemory | None:
        """
        Fetch a single memory by ID, strictly respecting workspace isolation.
        """
        with self._get_connection() as conn:
            if workspace_id:
                cursor = conn.execute(
                    "SELECT * FROM workforce_memories WHERE id = ? AND workspace_id = ? AND is_deleted = 0",
                    (memory_id, workspace_id),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM workforce_memories WHERE id = ? AND is_deleted = 0",
                    (memory_id,),
                )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_memory(cursor, row)

    def update_memory(
        self,
        memory_id: str,
        summary: str | None = None,
        content: str | None = None,
        category: MemoryCategory | str | None = None,
        tags: list[str] | None = None,
        confidence: float | None = None,
        workspace_id: str | None = None,
    ) -> WorkforceMemory:
        """
        Update an existing memory with sanitized parameters.
        """
        existing = self.get_memory(memory_id, workspace_id=workspace_id)
        if not existing:
            raise KeyError(f"Memory with ID '{memory_id}' not found.")

        new_summary = sanitize_memory_text(summary) if summary is not None else existing.summary
        new_content = sanitize_memory_text(content) if content is not None else existing.content
        new_cat = (
            (category if isinstance(category, MemoryCategory) else MemoryCategory.from_str(str(category)))
            if category is not None
            else existing.category
        )
        new_tags = [sanitize_memory_text(t) for t in tags] if tags is not None else existing.tags
        new_confidence = max(0.0, min(1.0, float(confidence))) if confidence is not None else existing.confidence
        now = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE workforce_memories
                SET summary = ?, content = ?, category = ?, tags = ?, confidence = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    new_summary,
                    new_content,
                    new_cat.value if isinstance(new_cat, MemoryCategory) else str(new_cat),
                    json.dumps(new_tags),
                    new_confidence,
                    now,
                    memory_id,
                ),
            )
            conn.commit()

        return self.get_memory(memory_id, workspace_id=workspace_id) # type: ignore[return-value]

    def archive_memory(self, memory_id: str, archived: bool = True, workspace_id: str | None = None) -> WorkforceMemory:
        """
        Toggle the archived state of a memory record.
        """
        existing = self.get_memory(memory_id, workspace_id=workspace_id)
        if not existing:
            raise KeyError(f"Memory with ID '{memory_id}' not found.")

        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE workforce_memories SET is_archived = ?, updated_at = ? WHERE id = ?",
                (1 if archived else 0, now, memory_id),
            )
            conn.commit()

        return self.get_memory(memory_id, workspace_id=workspace_id) # type: ignore[return-value]

    def delete_memory(self, memory_id: str, hard: bool = False, workspace_id: str | None = None) -> bool:
        """
        Delete a memory record (soft-delete by default, hard-delete if specified).
        """
        with self._get_connection() as conn:
            if hard:
                if workspace_id:
                    cursor = conn.execute("DELETE FROM workforce_memories WHERE id = ? AND workspace_id = ?", (memory_id, workspace_id))
                else:
                    cursor = conn.execute("DELETE FROM workforce_memories WHERE id = ?", (memory_id,))
            else:
                now = datetime.now(timezone.utc).isoformat()
                if workspace_id:
                    cursor = conn.execute(
                        "UPDATE workforce_memories SET is_deleted = 1, updated_at = ? WHERE id = ? AND workspace_id = ?",
                        (now, memory_id, workspace_id),
                    )
                else:
                    cursor = conn.execute("UPDATE workforce_memories SET is_deleted = 1, updated_at = ? WHERE id = ?", (now, memory_id))
            conn.commit()
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Query & Retrieval Operations
    # ------------------------------------------------------------------

    def list_memories(
        self,
        workspace_id: str,
        team_name: str | None = None,
        agent_name: str | None = None,
        mission_id: str | None = None,
        execution_id: str | None = None,
        category: str | None = None,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
        query: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkforceMemory]:
        """
        Lists memories with multi-dimensional filtering, always enforcing workspace isolation.
        """
        clauses = ["workspace_id = ?", "is_deleted = 0"]
        params: list[Any] = [workspace_id]

        if not include_archived:
            clauses.append("is_archived = 0")

        if team_name:
            clauses.append("(team_name = ? OR team_name IS NULL)")
            params.append(team_name)

        if agent_name:
            clauses.append("(agent_name = ? OR agent_name IS NULL)")
            params.append(agent_name)

        if mission_id:
            clauses.append("mission_id = ?")
            params.append(mission_id)

        if execution_id:
            clauses.append("execution_id = ?")
            params.append(execution_id)

        if category:
            clauses.append("category = ?")
            params.append(category.lower().strip())

        if categories:
            placeholders = ",".join(["?"] * len(categories))
            clauses.append(f"category IN ({placeholders})")
            params.extend([c.lower().strip() for c in categories])

        if query:
            clean_q = query.strip()
            clauses.append("(summary LIKE ? OR content LIKE ? OR tags LIKE ?)")
            q_param = f"%{clean_q}%"
            params.extend([q_param, q_param, q_param])

        where_sql = " AND ".join(clauses)
        sql = f"SELECT * FROM workforce_memories WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        memories: list[WorkforceMemory] = []
        with self._get_connection() as conn:
            cursor = conn.execute(sql, params)
            for row in cursor.fetchall():
                mem = self._row_to_memory(cursor, row)
                if tags:
                    # Filter in-memory if memory must match all requested tags
                    if all(t in mem.tags for t in tags):
                        memories.append(mem)
                else:
                    memories.append(mem)

        return memories

    def search_memories(
        self,
        workspace_id: str,
        query: str,
        team_name: str | None = None,
        agent_name: str | None = None,
        mission_id: str | None = None,
        execution_id: str | None = None,
        categories: list[str] | None = None,
        limit: int = 5,
    ) -> list[tuple[WorkforceMemory, float]]:
        """
        Performs deterministic keyword and relevance ranking over memories.
        Factors: token match density, tag exact match, category match, recency, confidence.
        """
        if not query or not query.strip():
            return []

        # Candidate selection from workspace
        candidates = self.list_memories(
            workspace_id=workspace_id,
            team_name=team_name,
            agent_name=agent_name,
            mission_id=mission_id,
            execution_id=execution_id,
            categories=categories,
            include_archived=False,
            limit=200,
        )

        query_tokens = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 2]
        if not query_tokens:
            query_tokens = [w.lower() for w in re.findall(r"\w+", query)]
        query_set = set(query_tokens)

        now_dt = datetime.now(timezone.utc)
        scored: list[tuple[WorkforceMemory, float]] = []

        for mem in candidates:
            score = 0.0
            summary_words = set(re.findall(r"\w+", mem.summary.lower()))
            content_words = set(re.findall(r"\w+", mem.content.lower()))
            tag_words = {t.lower() for t in mem.tags}

            # 1. Summary token overlap (weight: 2.5 per token)
            for token in query_set:
                if token in summary_words:
                    score += 2.5
                elif any(token in sw or sw in token for sw in summary_words if len(sw) >= 3):
                    score += 1.2

            # 2. Content token overlap (weight: 1.0 per token)
            for token in query_set:
                if token in content_words:
                    score += 1.0
                elif any(token in cw or cw in token for cw in content_words if len(cw) >= 3):
                    score += 0.5

            # 3. Exact tag matches (bonus: 2.0)
            tag_matches = sum(1 for t in query_tokens if t in tag_words)
            score += tag_matches * 2.0

            # 4. Direct Category match (bonus: 1.5)
            if mem.category.value in query_set:
                score += 1.5

            if score > 0.0:
                # 5. Recency boost (decay over days)
                try:
                    mem_dt = datetime.fromisoformat(mem.created_at)
                    age_days = max(0.0, (now_dt - mem_dt).total_seconds() / 86400.0)
                except Exception:
                    age_days = 0.0
                recency_multiplier = 1.0 / (1.0 + age_days * 0.02)

                # 6. Confidence weighting
                final_score = score * recency_multiplier * mem.confidence
                scored.append((mem, round(final_score, 3)))

        # Sort descending by score, then by created_at DESC
        scored.sort(key=lambda item: (item[1], item[0].created_at), reverse=True)
        return scored[:limit]

    def retrieve_for_task(
        self,
        workspace_id: str,
        task_instruction: str,
        agent_name: str | None = None,
        team_name: str | None = None,
        mission_id: str | None = None,
        limit: int = 5,
    ) -> list[WorkforceMemory]:
        """
        Convenience method to retrieve the top ranked memories for a task instruction.
        Returns plain WorkforceMemory list (no scores). Use retrieve_for_context() when
        scores are needed for threshold gating.
        """
        results = self.search_memories(
            workspace_id=workspace_id,
            query=task_instruction,
            team_name=team_name,
            agent_name=agent_name,
            mission_id=mission_id,
            limit=limit,
        )
        return [mem for mem, _ in results]

    def retrieve_for_context(
        self,
        workspace_id: str,
        task_instruction: str,
        agent_name: str | None = None,
        team_name: str | None = None,
        mission_id: str | None = None,
        limit: int = 10,
    ) -> list[tuple[WorkforceMemory, float]]:
        """
        Retrieve scored (memory, relevance_score) pairs for context injection.
        Unlike retrieve_for_task(), this preserves the relevance score so callers can
        apply threshold gating and budget-aware selection.

        Only non-archived, non-deleted, verified memories are candidates.
        Scoring is purely deterministic (term-overlap × recency × confidence).
        Same input always produces same output order.
        """
        return self.search_memories(
            workspace_id=workspace_id,
            query=task_instruction,
            team_name=team_name,
            agent_name=agent_name,
            mission_id=mission_id,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _row_to_memory(self, cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> WorkforceMemory:
        col_names = [d[0] for d in cursor.description]
        data = dict(zip(col_names, row))

        prov_raw = data.get("provenance")
        prov_dict = json.loads(prov_raw) if isinstance(prov_raw, str) else (prov_raw or {})
        prov_obj = MemoryProvenance.from_dict(prov_dict)

        tags_raw = data.get("tags")
        tags_list = json.loads(tags_raw) if isinstance(tags_raw, str) else (tags_raw or [])

        return WorkforceMemory(
            id=data["id"],
            workspace_id=data["workspace_id"],
            team_name=data.get("team_name"),
            agent_name=data.get("agent_name"),
            mission_id=data.get("mission_id"),
            execution_id=data.get("execution_id"),
            category=MemoryCategory.from_str(data["category"]),
            summary=data["summary"],
            content=data["content"],
            provenance=prov_obj,
            confidence=float(data.get("confidence", 1.0)),
            tags=tags_list,
            is_archived=bool(data.get("is_archived", 0)),
            is_deleted=bool(data.get("is_deleted", 0)),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
