"""
Agent Identity — persistent identity layer for agents.
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AgentIdentity:
    """Represents the persistent identity of an agent."""
    id: str
    name: str
    role: str
    created_at: float
    last_active: float

    @classmethod
    def create(cls, name: str, role: str) -> "AgentIdentity":
        """Generate a new AgentIdentity with a fresh ID and current timestamps."""
        safe_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        suffix = uuid.uuid4().hex[:8]
        agent_id = f"agent_{safe_name}_{suffix}"
        
        now = time.time()
        return cls(
            id=agent_id,
            name=name,
            role=role,
            created_at=now,
            last_active=now,
        )


class AgentStore:
    """SQLite-based storage for agent identities across sessions."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        if self.db_path == ":memory:":
            import uuid
            self.db_path = f"file:memdb_{uuid.uuid4().hex}?mode=memory&cache=shared"
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, uri=self.db_path.startswith("file:"))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_active REAL NOT NULL
                )
                """
            )
            # The 'name' column is UNIQUE to ensure we can look up an agent
            # strictly by its name within a team project.

    def save(self, identity: AgentIdentity) -> None:
        """
        Save or update an agent's identity. 
        If the name already exists, updates the role and last_active, preserving id and created_at.
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO agents (id, name, role, created_at, last_active)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    role=excluded.role,
                    last_active=excluded.last_active
                """,
                (identity.id, identity.name, identity.role, identity.created_at, identity.last_active),
            )

    def load_by_name(self, name: str) -> AgentIdentity | None:
        """Retrieve an identity by its name."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, name, role, created_at, last_active FROM agents WHERE name = ?",
                (name,)
            ).fetchone()
            
            if row is None:
                return None
                
            return AgentIdentity(
                id=row["id"],
                name=row["name"],
                role=row["role"],
                created_at=row["created_at"],
                last_active=row["last_active"],
            )

    def load(self, agent_id: str) -> AgentIdentity | None:
        """Retrieve an identity by its ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, name, role, created_at, last_active FROM agents WHERE id = ?",
                (agent_id,)
            ).fetchone()
            
            if row is None:
                return None
                
            return AgentIdentity(
                id=row["id"],
                name=row["name"],
                role=row["role"],
                created_at=row["created_at"],
                last_active=row["last_active"],
            )

    def list(self) -> list[AgentIdentity]:
        """List all identities in the store."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, name, role, created_at, last_active FROM agents ORDER BY name"
            ).fetchall()
            
            return [
                AgentIdentity(
                    id=row["id"],
                    name=row["name"],
                    role=row["role"],
                    created_at=row["created_at"],
                    last_active=row["last_active"],
                )
                for row in rows
            ]
