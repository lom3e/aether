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

from aether.personal.models import IntentTier, PersonalMessage, PersonalSession, PersonalStep

logger = logging.getLogger(__name__)


class PersonalStore:
    """SQLite-backed store for Personal Agent conversations and history."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
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

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None
