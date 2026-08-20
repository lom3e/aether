"""
SQLite — Hardened SQLite connection factory and concurrency configuration.
Configures WAL journal mode, busy timeouts, and synchronous modes for reliable concurrent access.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def configure_sqlite_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Configure standard pragmas on an active SQLite connection.

    Applies:
    - foreign_keys = ON
    - journal_mode = WAL (allows concurrent readers and writers without lock clashes)
    - busy_timeout = 5000 (waits up to 5 seconds when busy before raising OperationalError)
    - synchronous = NORMAL (safe & high-performance with WAL)
    """
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except sqlite3.OperationalError:
        pass
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def get_sqlite_connection(
    db_path: str | Path,
    *,
    timeout: float = 10.0,
    row_factory: type | None = sqlite3.Row,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Create and configure a SQLite connection with robust concurrency pragmas."""
    path_str = str(db_path)
    is_uri = path_str.startswith("file:")
    conn = sqlite3.connect(
        path_str,
        timeout=timeout,
        uri=is_uri,
        check_same_thread=check_same_thread,
    )
    if row_factory is not None:
        conn.row_factory = row_factory
    configure_sqlite_connection(conn)
    return conn
