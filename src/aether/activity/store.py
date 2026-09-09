"""
Persistent SQLite Storage for Aether Activity Feed (Phase C).
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

from aether.activity.models import ActivityCategory, ActivityEvent, ActivityStatus

logger = logging.getLogger(__name__)


class ActivityStore:
    """SQLite-backed store for human-centric activity events."""

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
                CREATE TABLE IF NOT EXISTS activity_events (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    status TEXT NOT NULL,
                    link_view TEXT,
                    link_id TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_act_ws ON activity_events(workspace_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_act_created ON activity_events(workspace_id, created_at DESC);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_act_cat ON activity_events(workspace_id, category);")

    def record_activity(self, event: ActivityEvent) -> ActivityEvent:
        """Records an activity event."""
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO activity_events (
                    id, workspace_id, title, description, category, status,
                    link_view, link_id, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.workspace_id,
                    event.title,
                    event.description,
                    event.category.value if isinstance(event.category, ActivityCategory) else str(event.category),
                    event.status.value if isinstance(event.status, ActivityStatus) else str(event.status),
                    event.link_view,
                    event.link_id,
                    json.dumps(event.metadata),
                    event.created_at,
                ),
            )
        return event

    def list_activities(
        self,
        workspace_id: str,
        category: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityEvent]:
        """Lists activities with optional filters and pagination."""
        conn = self._get_connection()
        conditions = ["workspace_id = ?"]
        params: list[Any] = [workspace_id]

        if category and category != "all":
            conditions.append("category = ?")
            params.append(category.lower().strip())

        if status and status != "all":
            conditions.append("status = ?")
            params.append(status.lower().strip())

        where_clause = " AND ".join(conditions)
        query = f"SELECT * FROM activity_events WHERE {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, limit), max(0, offset)])

        rows = conn.execute(query, params).fetchall()
        return [self._row_to_event(r) for r in rows]

    def _row_to_event(self, row: sqlite3.Row) -> ActivityEvent:
        return ActivityEvent(
            id=row["id"],
            workspace_id=row["workspace_id"],
            title=row["title"],
            description=row["description"],
            category=ActivityCategory.from_str(row["category"]),
            status=ActivityStatus.from_str(row["status"]),
            link_view=row["link_view"],
            link_id=row["link_id"],
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
