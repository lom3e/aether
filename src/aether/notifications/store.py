"""
SQLite persistence for Aether Universal Notification Fabric (Phase D).
Provides thread-safe WAL storage, indexing, and state management.
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

from aether.notifications.models import (
    Notification,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)

logger = logging.getLogger(__name__)


class NotificationStore:
    """SQLite-backed persistent store for notifications."""

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
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    link_view TEXT,
                    link_id TEXT,
                    action_required INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_notif_ws_status ON notifications(workspace_id, status, created_at DESC);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_notif_created ON notifications(created_at DESC);"
            )

    def save(self, notification: Notification) -> Notification:
        """Inserts or updates a notification."""
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO notifications (
                    id, workspace_id, type, title, message, priority,
                    status, link_view, link_id, action_required, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    notification.id,
                    notification.workspace_id,
                    notification.type.value if isinstance(notification.type, NotificationType) else str(notification.type),
                    notification.title,
                    notification.message,
                    notification.priority.value if isinstance(notification.priority, NotificationPriority) else str(notification.priority),
                    notification.status.value if isinstance(notification.status, NotificationStatus) else str(notification.status),
                    notification.link_view,
                    notification.link_id,
                    1 if notification.action_required else 0,
                    json.dumps(notification.metadata),
                    notification.created_at,
                ),
            )
        return notification

    def get(self, notification_id: str) -> Notification | None:
        """Retrieves a single notification by ID."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM notifications WHERE id = ?", (notification_id,)).fetchone()
        if not row:
            return None
        return self._row_to_notification(row)

    def list(
        self,
        workspace_id: str,
        status: str | None = None,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        """Lists notifications for a workspace, optionally filtered by status."""
        conn = self._get_connection()
        params: list[Any] = [workspace_id]
        sql = "SELECT * FROM notifications WHERE workspace_id = ?"

        if unread_only:
            sql += " AND status = ?"
            params.append(NotificationStatus.UNREAD.value)
        elif status:
            sql += " AND status = ?"
            params.append(status)
        else:
            sql += " AND status != ?"
            params.append(NotificationStatus.DISMISSED.value)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, limit))

        rows = conn.execute(sql, params).fetchall()
        return [self._row_to_notification(r) for r in rows]

    def mark_as_read(self, notification_id: str) -> bool:
        """Marks a notification as read."""
        with self._transaction() as cursor:
            cursor.execute(
                "UPDATE notifications SET status = ? WHERE id = ?",
                (NotificationStatus.READ.value, notification_id),
            )
            return cursor.rowcount > 0

    def mark_all_read(self, workspace_id: str) -> int:
        """Marks all unread notifications in a workspace as read."""
        with self._transaction() as cursor:
            cursor.execute(
                "UPDATE notifications SET status = ? WHERE workspace_id = ? AND status = ?",
                (NotificationStatus.READ.value, workspace_id, NotificationStatus.UNREAD.value),
            )
            return cursor.rowcount

    def dismiss(self, notification_id: str) -> bool:
        """Dismisses a notification."""
        with self._transaction() as cursor:
            cursor.execute(
                "UPDATE notifications SET status = ? WHERE id = ?",
                (NotificationStatus.DISMISSED.value, notification_id),
            )
            return cursor.rowcount > 0

    def get_unread_count(self, workspace_id: str) -> int:
        """Returns the number of unread notifications for a workspace."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM notifications WHERE workspace_id = ? AND status = ?",
            (workspace_id, NotificationStatus.UNREAD.value),
        ).fetchone()
        return int(row["cnt"]) if row else 0

    def _row_to_notification(self, row: sqlite3.Row) -> Notification:
        return Notification(
            id=row["id"],
            workspace_id=row["workspace_id"],
            type=NotificationType.from_str(row["type"]),
            title=row["title"],
            message=row["message"],
            priority=NotificationPriority.from_str(row["priority"]),
            status=NotificationStatus.from_str(row["status"]),
            link_view=row["link_view"],
            link_id=row["link_id"],
            action_required=bool(row["action_required"]),
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
