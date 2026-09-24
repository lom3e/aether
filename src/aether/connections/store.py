"""
Persistent SQLite Storage for Aether Connections and External Entities (Phase C).
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

from aether.connections.models import CalendarEvent, Connection, ConnectionStatus

logger = logging.getLogger(__name__)


class ConnectionStore:
    """SQLite-backed store for external tool connections and cached/synced entities."""

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
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    account_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    scopes TEXT,
                    capabilities TEXT,
                    auth_metadata TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conn_ws ON connections(workspace_id);")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_conn_ws_provider ON connections(workspace_id, provider);")

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS calendar_events (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    connection_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    description TEXT,
                    location TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cal_ws ON calendar_events(workspace_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cal_time ON calendar_events(workspace_id, start_time DESC);")

    def save_connection(self, conn: Connection) -> Connection:
        """Saves or updates a connection."""
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO connections (
                    id, workspace_id, provider, account_name, status,
                    scopes, capabilities, auth_metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conn.id,
                    conn.workspace_id,
                    conn.provider,
                    conn.account_name,
                    conn.status.value if isinstance(conn.status, ConnectionStatus) else str(conn.status),
                    json.dumps(conn.scopes),
                    json.dumps(conn.capabilities),
                    json.dumps(conn.auth_metadata),
                    conn.created_at,
                    conn.updated_at,
                ),
            )
        return conn

    save = save_connection

    def get_connection(self, connection_id: str) -> Connection | None:
        """Retrieves connection by ID."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM connections WHERE id = ?", (connection_id,)).fetchone()
        if not row:
            return None
        return self._row_to_connection(row)

    def get_connection_by_provider(self, workspace_id: str, provider: str) -> Connection | None:
        """Retrieves connection by workspace and provider."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM connections WHERE workspace_id = ? AND provider = ?",
            (workspace_id, provider),
        ).fetchone()
        if not row:
            return None
        return self._row_to_connection(row)

    def list_connections(self, workspace_id: str) -> list[Connection]:
        """Lists all connections for a workspace."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM connections WHERE workspace_id = ? ORDER BY provider ASC",
            (workspace_id,),
        ).fetchall()
        return [self._row_to_connection(r) for r in rows]

    def delete_connection(self, connection_id: str) -> None:
        """Deletes a connection."""
        with self._transaction() as cursor:
            cursor.execute("DELETE FROM connections WHERE id = ?", (connection_id,))

    def save_calendar_event(self, event: CalendarEvent) -> CalendarEvent:
        """Saves a real calendar event."""
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO calendar_events (
                    id, workspace_id, connection_id, title, start_time,
                    end_time, description, location, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.workspace_id,
                    event.connection_id,
                    event.title,
                    event.start_time,
                    event.end_time,
                    event.description,
                    event.location,
                    event.created_at,
                ),
            )
        return event

    def list_calendar_events(
        self,
        workspace_id: str,
        limit: int = 50,
    ) -> list[CalendarEvent]:
        """Lists calendar events ordered by start_time."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM calendar_events WHERE workspace_id = ? ORDER BY start_time ASC LIMIT ?",
            (workspace_id, max(1, limit)),
        ).fetchall()
        return [
            CalendarEvent(
                id=r["id"],
                workspace_id=r["workspace_id"],
                connection_id=r["connection_id"],
                title=r["title"],
                start_time=r["start_time"],
                end_time=r["end_time"],
                description=r["description"] or "",
                location=r["location"] or "",
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def _row_to_connection(self, row: sqlite3.Row) -> Connection:
        return Connection(
            id=row["id"],
            workspace_id=row["workspace_id"],
            provider=row["provider"],
            account_name=row["account_name"],
            status=ConnectionStatus.from_str(row["status"]),
            scopes=json.loads(row["scopes"]) if row["scopes"] else [],
            capabilities=json.loads(row["capabilities"]) if row["capabilities"] else [],
            auth_metadata=json.loads(row["auth_metadata"]) if row["auth_metadata"] else {},
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
