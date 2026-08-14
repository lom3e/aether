"""
ConversationStore — SQLite-backed persistence for multi-turn conversations and sessions.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ConversationStore:
    """
    Manages multiple persistent conversations within a workspace.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        if self.db_path == ":memory:":
            self.db_path = f"file:memdb_convs_{uuid.uuid4().hex}?mode=memory&cache=shared"
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, uri=self.db_path.startswith("file:"))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    team_name TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_message TEXT,
                    agents TEXT DEFAULT '[]'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_ui_messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    agent_name TEXT,
                    content TEXT,
                    created_at TEXT NOT NULL,
                    metadata TEXT,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_updated ON conversations(updated_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_conv ON conversation_ui_messages(conversation_id, created_at ASC)")

    def create(
        self,
        title: str = "New Conversation",
        team_name: str | None = None,
        conv_id: str | None = None,
        status: str = "active",
        agents: list[str] | None = None,
    ) -> dict[str, Any]:
        cid = conv_id or uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        agents_json = json.dumps(agents or [])

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO conversations (id, title, team_name, status, created_at, updated_at, last_message, agents)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    updated_at = excluded.updated_at
                """,
                (cid, title, team_name, status, now, now, "", agents_json),
            )

        return {
            "id": cid,
            "title": title,
            "team_name": team_name,
            "status": status,
            "created_at": now,
            "updated_at": now,
            "last_message": "",
            "agents": agents or [],
        }

    def list(self, search: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            if search and search.strip():
                pattern = f"%{search.strip()}%"
                rows = conn.execute(
                    """
                    SELECT id, title, team_name, status, created_at, updated_at, last_message, agents
                    FROM conversations
                    WHERE title LIKE ? OR last_message LIKE ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (pattern, pattern, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, title, team_name, status, created_at, updated_at, last_message, agents
                    FROM conversations
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        result = []
        for r in rows:
            agents_list = []
            try:
                agents_list = json.loads(r["agents"] or "[]")
            except Exception:
                pass
            result.append({
                "id": r["id"],
                "title": r["title"],
                "team_name": r["team_name"],
                "status": r["status"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "last_message": r["last_message"] or "",
                "agents": agents_list,
            })
        return result

    def get(self, conv_id: str) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, title, team_name, status, created_at, updated_at, last_message, agents FROM conversations WHERE id = ?",
                (conv_id,),
            ).fetchone()

        if not row:
            return None

        agents_list = []
        try:
            agents_list = json.loads(row["agents"] or "[]")
        except Exception:
            pass

        messages = self.get_messages(conv_id)

        return {
            "id": row["id"],
            "title": row["title"],
            "team_name": row["team_name"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_message": row["last_message"] or "",
            "agents": agents_list,
            "messages": messages,
        }

    def update(
        self,
        conv_id: str,
        title: str | None = None,
        status: str | None = None,
        last_message: str | None = None,
        agents: list[str] | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            existing = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
            if not existing:
                return None

            new_title = title if title is not None else existing["title"]
            new_status = status if status is not None else existing["status"]
            new_last = last_message if last_message is not None else existing["last_message"]
            new_agents = json.dumps(agents) if agents is not None else existing["agents"]

            conn.execute(
                """
                UPDATE conversations
                SET title = ?, status = ?, last_message = ?, agents = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_title, new_status, new_last, new_agents, now, conv_id),
            )

        return self.get(conv_id)

    def delete(self, conv_id: str) -> bool:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM conversation_ui_messages WHERE conversation_id = ?", (conv_id,))
            cursor = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            return cursor.rowcount > 0

    def add_message(
        self,
        conv_id: str,
        role: str,
        content: str,
        agent_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        msg_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})

        with self._get_connection() as conn:
            # Ensure conversation exists
            existing = conn.execute("SELECT id, title, agents FROM conversations WHERE id = ?", (conv_id,)).fetchone()
            if not existing:
                # Create default conversation with title snippet
                title = content.splitlines()[0][:60].strip() or "New Task"
                agents_init = [agent_name] if agent_name else []
                conn.execute(
                    """
                    INSERT INTO conversations (id, title, team_name, status, created_at, updated_at, last_message, agents)
                    VALUES (?, ?, ?, 'active', ?, ?, ?, ?)
                    """,
                    (conv_id, title, None, now, now, content[:120], json.dumps(agents_init)),
                )
            else:
                # Update agents set and last_message
                curr_agents = []
                try:
                    curr_agents = json.loads(existing["agents"] or "[]")
                except Exception:
                    pass
                if agent_name and agent_name not in curr_agents:
                    curr_agents.append(agent_name)

                # Generate a meaningful title if currently default
                current_title = existing["title"]
                if current_title in ("New Task", "New Conversation") and role == "user":
                    current_title = content.splitlines()[0][:60].strip() or current_title

                conn.execute(
                    """
                    UPDATE conversations
                    SET last_message = ?, updated_at = ?, agents = ?, title = ?
                    WHERE id = ?
                    """,
                    (content[:120], now, json.dumps(curr_agents), current_title, conv_id),
                )

            conn.execute(
                """
                INSERT INTO conversation_ui_messages (id, conversation_id, role, agent_name, content, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (msg_id, conv_id, role, agent_name, content, now, meta_json),
            )

        return {
            "id": msg_id,
            "conversation_id": conv_id,
            "role": role,
            "agent_name": agent_name,
            "content": content,
            "created_at": now,
            "metadata": metadata or {},
        }

    def get_messages(self, conv_id: str) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, conversation_id, role, agent_name, content, created_at, metadata
                FROM conversation_ui_messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                """,
                (conv_id,),
            ).fetchall()

        messages = []
        for r in rows:
            meta = {}
            try:
                meta = json.loads(r["metadata"] or "{}")
            except Exception:
                pass
            messages.append({
                "id": r["id"],
                "conversation_id": r["conversation_id"],
                "role": r["role"],
                "agent_name": r["agent_name"],
                "content": r["content"] or "",
                "created_at": r["created_at"],
                "metadata": meta,
            })
        return messages
