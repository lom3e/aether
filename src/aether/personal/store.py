"""
Persistent SQLite Storage for Personal Agent Conversations (Phase C).
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import logging
from pathlib import Path
import sqlite3
import threading
from typing import Any, Generator
import uuid

from aether.personal.models import (
    IntentTier,
    PersonalMessage,
    PersonalSession,
    PersonalStep,
    PersonalTask,
    PersonalTaskStatus,
)

logger = logging.getLogger(__name__)


class PersonalStore:
    """SQLite-backed store for Personal Agent conversations and history."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._conns_lock = threading.Lock()
        self._all_conns: set[sqlite3.Connection] = set()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=10.0,
                check_same_thread=False,
                isolation_level=None,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute("PRAGMA foreign_keys = ON;")
            with self._conns_lock:
                self._all_conns.add(conn)
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        conn = self._get_connection()
        conn.execute("BEGIN IMMEDIATE;")
        cursor = conn.cursor()
        try:
            yield cursor
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def _init_db(self) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS personal_sessions (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ps_ws ON personal_sessions(workspace_id);")

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS personal_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    steps TEXT,
                    action_execution_id TEXT,
                    mission_id TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES personal_sessions(id) ON DELETE CASCADE
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pm_session ON personal_messages(session_id, created_at ASC);")

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS personal_tasks (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    progress_percent INTEGER NOT NULL DEFAULT 0,
                    current_step TEXT,
                    result_summary TEXT,
                    mission_id TEXT,
                    action_execution_id TEXT,
                    error TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pt_ws_status ON personal_tasks(workspace_id, status, updated_at DESC);")

    def save_session(self, session: PersonalSession) -> PersonalSession:
        """Saves or updates session metadata."""
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO personal_sessions (
                    id, workspace_id, title, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.workspace_id,
                    session.title,
                    session.created_at,
                    session.updated_at,
                ),
            )
        return session

    def get_session(self, session_id: str) -> PersonalSession | None:
        """Retrieves a session and all its messages."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM personal_sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return None

        msg_rows = conn.execute(
            "SELECT * FROM personal_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()

        messages = [self._row_to_message(r) for r in msg_rows]

        return PersonalSession(
            id=row["id"],
            workspace_id=row["workspace_id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            messages=messages,
        )

    def list_sessions(self, workspace_id: str, limit: int = 20) -> list[PersonalSession]:
        """Lists recent sessions."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM personal_sessions WHERE workspace_id = ? ORDER BY updated_at DESC LIMIT ?",
            (workspace_id, max(1, limit)),
        ).fetchall()

        return [
            PersonalSession(
                id=r["id"],
                workspace_id=r["workspace_id"],
                title=r["title"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                messages=[],
            )
            for r in rows
        ]

    def add_message(self, message: PersonalMessage) -> PersonalMessage:
        """Adds a message to a session."""
        if not self.get_session(message.session_id):
            self.save_session(
                PersonalSession(
                    id=message.session_id,
                    workspace_id=message.workspace_id,
                    title=f"Session {message.session_id[:8]}",
                )
            )
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO personal_messages (
                    id, session_id, workspace_id, role, content, tier,
                    steps, action_execution_id, mission_id, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.session_id,
                    message.workspace_id,
                    message.role,
                    message.content,
                    message.tier.value if isinstance(message.tier, IntentTier) else str(message.tier),
                    json.dumps([s.to_dict() for s in message.steps]),
                    message.action_execution_id,
                    message.mission_id,
                    json.dumps(message.metadata),
                    message.created_at,
                ),
            )
            cursor.execute(
                "UPDATE personal_sessions SET updated_at = ? WHERE id = ?",
                (message.created_at, message.session_id),
            )
        return message

    def _row_to_message(self, row: sqlite3.Row) -> PersonalMessage:
        raw_steps = json.loads(row["steps"]) if row["steps"] else []
        steps = [PersonalStep.from_dict(s) for s in raw_steps]

        return PersonalMessage(
            id=row["id"],
            session_id=row["session_id"],
            workspace_id=row["workspace_id"],
            role=row["role"],
            content=row["content"],
            tier=IntentTier.from_str(row["tier"]),
            steps=steps,
            action_execution_id=row["action_execution_id"],
            mission_id=row["mission_id"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
        )

    def get_messages(self, session_id: str) -> list[PersonalMessage]:
        """Retrieves all messages for a session ordered by creation time."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM personal_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def get_recent_messages(self, session_id: str, limit: int = 6) -> list[PersonalMessage]:
        """Retrieves the most recent messages for conversational context."""
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT * FROM (
                SELECT * FROM personal_messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?
            ) ORDER BY created_at ASC
            """,
            (session_id, max(1, limit)),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def save_task(self, task: PersonalTask) -> PersonalTask:
        """Inserts or updates a persistent personal task."""
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO personal_tasks (
                    id, session_id, workspace_id, title, status, tier,
                    progress_percent, current_step, result_summary, mission_id,
                    action_execution_id, error, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.session_id,
                    task.workspace_id,
                    task.title,
                    task.status.value if isinstance(task.status, PersonalTaskStatus) else str(task.status),
                    task.tier.value if isinstance(task.tier, IntentTier) else str(task.tier),
                    task.progress_percent,
                    task.current_step,
                    task.result_summary,
                    task.mission_id,
                    task.action_execution_id,
                    task.error,
                    json.dumps(task.metadata),
                    task.created_at,
                    task.updated_at,
                ),
            )
        return task

    def get_task(self, task_id: str) -> PersonalTask | None:
        """Retrieves a personal task by ID."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM personal_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return None
        return self._row_to_task(row)

    def list_tasks(
        self,
        workspace_id: str,
        session_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[PersonalTask]:
        """Lists personal tasks for a workspace, optionally filtered by session or status."""
        conn = self._get_connection()
        conditions = ["workspace_id = ?"]
        params: list[Any] = [workspace_id]

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where_clause = " AND ".join(conditions)
        sql = f"SELECT * FROM personal_tasks WHERE {where_clause} ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, limit))

        rows = conn.execute(sql, params).fetchall()
        return [self._row_to_task(r) for r in rows]

    def update_task_progress(
        self,
        task_id: str,
        progress_percent: int,
        current_step: str,
        status: PersonalTaskStatus | str | None = None,
        result_summary: str | None = None,
        error: str | None = None,
    ) -> PersonalTask | None:
        """Updates progress, step, status, and outcome of a personal task."""
        task = self.get_task(task_id)
        if not task:
            return None

        task.progress_percent = progress_percent
        task.current_step = current_step
        if status:
            task.status = status if isinstance(status, PersonalTaskStatus) else PersonalTaskStatus.from_str(str(status))
        if result_summary is not None:
            task.result_summary = result_summary
        if error is not None:
            task.error = error
        task.updated_at = task.updated_at = str(task.created_at)  # refreshed below
        from datetime import datetime, timezone
        task.updated_at = datetime.now(timezone.utc).isoformat()

        return self.save_task(task)

    def _row_to_task(self, row: sqlite3.Row) -> PersonalTask:
        return PersonalTask(
            id=row["id"],
            session_id=row["session_id"],
            workspace_id=row["workspace_id"],
            title=row["title"],
            status=PersonalTaskStatus.from_str(row["status"]),
            tier=IntentTier.from_str(row["tier"]),
            progress_percent=int(row["progress_percent"]),
            current_step=row["current_step"] or "",
            result_summary=row["result_summary"],
            mission_id=row["mission_id"],
            action_execution_id=row["action_execution_id"],
            error=row["error"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def close(self) -> None:
        with self._conns_lock:
            for conn in list(self._all_conns):
                try:
                    conn.close()
                except Exception:
                    pass
            self._all_conns.clear()
        if hasattr(self._local, "conn"):
            self._local.conn = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
