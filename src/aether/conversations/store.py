"""
ConversationStore — SQLite-backed persistence for multi-turn conversations and sessions.
Supports full conversation lifecycle: creation, editing, deletion, archiving, duplication, activities timeline, unread state, and search.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def generate_smart_title(content: str) -> str:
    """Generate a clean, human-readable title from a prompt message."""
    if not content or not content.strip():
        return "New Task"
    clean = content.strip().splitlines()[0].strip()
    clean = re.sub(r"^[#\*\-–—\d\.\s]+", "", clean).strip()
    if len(clean) > 48:
        words = clean[:45].rsplit(" ", 1)
        clean = (words[0] if len(words) > 1 else clean[:45]) + "..."
    return clean.capitalize() if clean else "New Task"


from aether.core.sqlite import get_sqlite_connection


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
        return get_sqlite_connection(self.db_path)

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
                    agents TEXT DEFAULT '[]',
                    unread INTEGER DEFAULT 0
                )
                """
            )
            try:
                conn.execute("ALTER TABLE conversations ADD COLUMN unread INTEGER DEFAULT 0")
            except Exception:
                pass

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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_activities (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    activity_type TEXT NOT NULL,
                    message TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_updated ON conversations(updated_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_status ON conversations(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_conv ON conversation_ui_messages(conversation_id, created_at ASC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_content ON conversation_ui_messages(content)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_act_conv ON conversation_activities(conversation_id, created_at ASC)")

    def create(
        self,
        title: str = "New Task",
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
                INSERT INTO conversations (id, title, team_name, status, created_at, updated_at, last_message, agents, unread)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
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
            "unread": False,
            "messages": [],
            "activities": [],
        }

    def list(
        self,
        search: str | None = None,
        status: str | None = None,
        include_archived: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT id, title, team_name, status, created_at, updated_at, last_message, agents, unread FROM conversations WHERE 1=1"
        params: list[Any] = []

        if not include_archived:
            query += " AND status != 'archived'"

        if status:
            query += " AND status = ?"
            params.append(status)

        if search and search.strip():
            term = f"%{search.strip()}%"
            query += """
                AND (
                    title LIKE ? OR last_message LIKE ? OR id IN (
                        SELECT DISTINCT conversation_id FROM conversation_ui_messages WHERE content LIKE ?
                    )
                )
            """
            params.extend([term, term, term])

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        results = []
        for r in rows:
            agents_list = []
            try:
                agents_list = json.loads(r["agents"] or "[]")
            except Exception:
                pass
            results.append({
                "id": r["id"],
                "title": r["title"],
                "team_name": r["team_name"],
                "status": r["status"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "last_message": r["last_message"] or "",
                "agents": agents_list,
                "unread": bool(r["unread"] if "unread" in r.keys() else 0),
            })
        return results

    def get(self, conv_id: str) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, title, team_name, status, created_at, updated_at, last_message, agents, unread FROM conversations WHERE id = ?",
                (conv_id,),
            ).fetchone()
            if not row:
                return None

            msg_rows = conn.execute(
                "SELECT id, role, agent_name, content, created_at, metadata FROM conversation_ui_messages WHERE conversation_id = ? ORDER BY created_at ASC",
                (conv_id,),
            ).fetchall()

            act_rows = conn.execute(
                "SELECT id, agent, activity_type, message, metadata, created_at FROM conversation_activities WHERE conversation_id = ? ORDER BY created_at ASC",
                (conv_id,),
            ).fetchall()

        agents_list = []
        try:
            agents_list = json.loads(row["agents"] or "[]")
        except Exception:
            pass

        messages = []
        for m in msg_rows:
            meta = {}
            try:
                meta = json.loads(m["metadata"] or "{}")
            except Exception:
                pass
            messages.append({
                "id": m["id"],
                "role": m["role"],
                "agent_name": m["agent_name"],
                "content": m["content"],
                "created_at": m["created_at"],
                "metadata": meta,
            })

        activities = []
        for a in act_rows:
            meta = {}
            try:
                meta = json.loads(a["metadata"] or "{}")
            except Exception:
                pass
            activities.append({
                "id": a["id"],
                "agent": a["agent"],
                "type": a["activity_type"],
                "message": a["message"] or "",
                "metadata": meta,
                "timestamp": a["created_at"],
            })

        return {
            "id": row["id"],
            "title": row["title"],
            "team_name": row["team_name"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_message": row["last_message"] or "",
            "agents": agents_list,
            "unread": bool(row["unread"] if "unread" in row.keys() else 0),
            "messages": messages,
            "activities": activities,
        }

    def mark_read(self, conv_id: str) -> None:
        """Mark conversation as read."""
        with self._get_connection() as conn:
            conn.execute("UPDATE conversations SET unread = 0 WHERE id = ?", (conv_id,))

    def get_messages(self, conv_id: str) -> list[dict[str, Any]]:
        """Retrieve all persisted UI messages for a given conversation ID."""
        with self._get_connection() as conn:
            msg_rows = conn.execute(
                "SELECT id, role, agent_name, content, created_at, metadata FROM conversation_ui_messages WHERE conversation_id = ? ORDER BY created_at ASC",
                (conv_id,),
            ).fetchall()

        messages = []
        for m in msg_rows:
            meta = {}
            try:
                meta = json.loads(m["metadata"] or "{}")
            except Exception:
                pass
            messages.append({
                "id": m["id"],
                "role": m["role"],
                "agent_name": m["agent_name"],
                "content": m["content"],
                "created_at": m["created_at"],
                "metadata": meta,
            })
        return messages

    def update(
        self,
        conv_id: str,
        title: str | None = None,
        status: str | None = None,
        last_message: str | None = None,
        agents: list[str] | None = None,
        unread: bool | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT title, status, last_message, agents, unread FROM conversations WHERE id = ?",
                (conv_id,),
            ).fetchone()
            if not row:
                return None

            new_title = title if title is not None else row["title"]
            new_status = status if status is not None else row["status"]
            new_last = last_message if last_message is not None else row["last_message"]
            new_agents = json.dumps(agents) if agents is not None else row["agents"]
            new_unread = int(unread) if unread is not None else row["unread"]

            conn.execute(
                """
                UPDATE conversations
                SET title = ?, status = ?, last_message = ?, agents = ?, unread = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_title, new_status, new_last, new_agents, new_unread, now, conv_id),
            )

        return self.get(conv_id)

    def archive(self, conv_id: str, archived: bool = True) -> dict[str, Any] | None:
        """Mark a conversation as archived or restore it to active/completed."""
        status = "archived" if archived else "completed"
        return self.update(conv_id, status=status)

    def duplicate(self, conv_id: str) -> dict[str, Any] | None:
        """Duplicate a conversation, message history, and activity events."""
        existing = self.get(conv_id)
        if not existing:
            return None
        new_title = f"{existing['title']} (Copy)"
        new_conv = self.create(
            title=new_title,
            team_name=existing.get("team_name"),
            agents=existing.get("agents"),
        )
        for msg in existing.get("messages", []):
            self.add_message(
                conv_id=new_conv["id"],
                role=msg["role"],
                content=msg["content"],
                agent_name=msg.get("agent_name"),
                metadata=msg.get("metadata"),
            )
        for act in existing.get("activities", []):
            self.add_activity(
                conv_id=new_conv["id"],
                agent=act["agent"],
                activity_type=act["type"],
                message=act.get("message", ""),
                metadata=act.get("metadata"),
            )
        return self.get(new_conv["id"])

    def delete(self, conv_id: str) -> bool:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM conversation_ui_messages WHERE conversation_id = ?", (conv_id,))
            conn.execute("DELETE FROM conversation_activities WHERE conversation_id = ?", (conv_id,))
            res = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            return res.rowcount > 0

    def add_activity(
        self,
        conv_id: str,
        agent: str,
        activity_type: str,
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist a live or recorded activity event into the conversation timeline."""
        act_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO conversation_activities (id, conversation_id, agent, activity_type, message, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (act_id, conv_id, agent, activity_type, message, meta_json, now),
            )

        return {
            "id": act_id,
            "conversation_id": conv_id,
            "agent": agent,
            "type": activity_type,
            "message": message,
            "metadata": metadata or {},
            "timestamp": now,
        }

    def get_activities(self, conv_id: str) -> list[dict[str, Any]]:
        """Retrieve persisted workforce activities for a conversation."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, agent, activity_type, message, metadata, created_at FROM conversation_activities WHERE conversation_id = ? ORDER BY created_at ASC",
                (conv_id,),
            ).fetchall()

        results = []
        for a in rows:
            meta = {}
            try:
                meta = json.loads(a["metadata"] or "{}")
            except Exception:
                pass
            results.append({
                "id": a["id"],
                "agent": a["agent"],
                "type": a["activity_type"],
                "message": a["message"] or "",
                "metadata": meta,
                "timestamp": a["created_at"],
            })
        return results

    def add_message(
        self,
        conv_id: str,
        role: str,
        content: str,
        agent_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Add a single message and update conversation metadata atomically."""
        msg_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})
        unread_flag = 1 if role == "assistant" else 0

        with self._get_connection() as conn:
            existing = conn.execute("SELECT id, title, agents, unread FROM conversations WHERE id = ?", (conv_id,)).fetchone()
            if not existing:
                title = generate_smart_title(content)
                agents_init = [agent_name] if agent_name else []
                conn.execute(
                    """
                    INSERT INTO conversations (id, title, team_name, status, created_at, updated_at, last_message, agents, unread)
                    VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?)
                    """,
                    (conv_id, title, None, now, now, content[:120], json.dumps(agents_init), unread_flag),
                )
            else:
                curr_agents = []
                try:
                    curr_agents = json.loads(existing["agents"] or "[]")
                except Exception:
                    pass
                if agent_name and agent_name not in curr_agents:
                    curr_agents.append(agent_name)

                current_title = existing["title"]
                if current_title in ("New Task", "New Conversation", "Nuovo Task") and role == "user":
                    current_title = generate_smart_title(content)

                conn.execute(
                    """
                    UPDATE conversations
                    SET last_message = ?, updated_at = ?, agents = ?, title = ?, unread = ?
                    WHERE id = ?
                    """,
                    (content[:120], now, json.dumps(curr_agents), current_title, unread_flag, conv_id),
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

    def edit_message(
        self,
        conv_id: str,
        message_id: str,
        new_content: str,
        truncate_after: bool = True,
    ) -> dict[str, Any] | None:
        """Edit a message and invalidate subsequent future messages in that turn."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            msg = conn.execute(
                "SELECT id, conversation_id, created_at, role FROM conversation_ui_messages WHERE id = ? AND conversation_id = ?",
                (message_id, conv_id),
            ).fetchone()
            if not msg:
                return None

            conn.execute(
                "UPDATE conversation_ui_messages SET content = ? WHERE id = ?",
                (new_content, message_id),
            )

            if truncate_after:
                conn.execute(
                    "DELETE FROM conversation_ui_messages WHERE conversation_id = ? AND created_at > ?",
                    (conv_id, msg["created_at"]),
                )

            last_row = conn.execute(
                "SELECT content FROM conversation_ui_messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1",
                (conv_id,),
            ).fetchone()
            last_text = last_row["content"][:120] if last_row else ""

            conn.execute(
                "UPDATE conversations SET last_message = ?, updated_at = ? WHERE id = ?",
                (last_text, now, conv_id),
            )

        return self.get(conv_id)

    def delete_message(self, conv_id: str, message_id: str, truncate_after: bool = False) -> dict[str, Any] | None:
        """Delete a single message from history, optionally truncating subsequent messages."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            msg = conn.execute(
                "SELECT id, conversation_id, created_at, role FROM conversation_ui_messages WHERE id = ? AND conversation_id = ?",
                (message_id, conv_id),
            ).fetchone()
            if not msg:
                return self.get(conv_id)

            conn.execute(
                "DELETE FROM conversation_ui_messages WHERE id = ? AND conversation_id = ?",
                (message_id, conv_id),
            )
            if truncate_after:
                conn.execute(
                    "DELETE FROM conversation_ui_messages WHERE conversation_id = ? AND created_at > ?",
                    (conv_id, msg["created_at"]),
                )

            last_row = conn.execute(
                "SELECT content FROM conversation_ui_messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1",
                (conv_id,),
            ).fetchone()
            last_text = last_row["content"][:120] if last_row else ""

            conn.execute(
                "UPDATE conversations SET last_message = ?, updated_at = ? WHERE id = ?",
                (last_text, now, conv_id),
            )

        return self.get(conv_id)
