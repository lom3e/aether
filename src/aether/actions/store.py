"""
Persistent SQLite Storage for Aether Action Executions (Phase C).
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
import threading
from typing import Any, Generator
import uuid

from aether.actions.models import ActionExecution, ActionExecutionStatus

logger = logging.getLogger(__name__)


class ActionStore:
    """SQLite-backed store for action executions and approval states."""

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
                CREATE TABLE IF NOT EXISTS action_executions (
                    id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_data TEXT,
                    output_data TEXT,
                    error_message TEXT,
                    approved_by TEXT,
                    rejection_reason TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    metadata TEXT
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ax_ws ON action_executions(workspace_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ax_status ON action_executions(workspace_id, status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ax_created ON action_executions(workspace_id, created_at DESC);")

    def save_execution(self, execution: ActionExecution) -> ActionExecution:
        """Saves or updates an action execution."""
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO action_executions (
                    id, action_id, workspace_id, status, input_data, output_data,
                    error_message, approved_by, rejection_reason, created_at,
                    completed_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution.id,
                    execution.action_id,
                    execution.workspace_id,
                    execution.status.value if isinstance(execution.status, ActionExecutionStatus) else str(execution.status),
                    json.dumps(execution.input_data),
                    json.dumps(execution.output_data),
                    execution.error_message,
                    execution.approved_by,
                    execution.rejection_reason,
                    execution.created_at,
                    execution.completed_at,
                    json.dumps(execution.metadata),
                ),
            )
        return execution

    def get_execution(self, execution_id: str) -> ActionExecution | None:
        """Retrieves a single execution by ID."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM action_executions WHERE id = ?", (execution_id,)).fetchone()
        if not row:
            return None
        return self._row_to_execution(row)

    def list_executions(
        self,
        workspace_id: str,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActionExecution]:
        """Lists executions for a workspace with optional status filter."""
        conn = self._get_connection()
        conditions = ["workspace_id = ?"]
        params: list[Any] = [workspace_id]

        if status and status != "all":
            conditions.append("status = ?")
            params.append(status.lower().strip())

        where_clause = " AND ".join(conditions)
        query = f"SELECT * FROM action_executions WHERE {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, limit), max(0, offset)])

        rows = conn.execute(query, params).fetchall()
        return [self._row_to_execution(r) for r in rows]

    def _row_to_execution(self, row: sqlite3.Row) -> ActionExecution:
        return ActionExecution(
            id=row["id"],
            action_id=row["action_id"],
            workspace_id=row["workspace_id"],
            status=ActionExecutionStatus.from_str(row["status"]),
            input_data=json.loads(row["input_data"]) if row["input_data"] else {},
            output_data=json.loads(row["output_data"]) if row["output_data"] else {},
            error_message=row["error_message"],
            approved_by=row["approved_by"],
            rejection_reason=row["rejection_reason"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None
