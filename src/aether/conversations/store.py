"""
ConversationStore — SQLite-backed persistence for multi-turn conversations, projects, and sessions.
Supports full conversation lifecycle: creation, editing, deletion, archiving, duplication,
pin/unpin, project organization, activities timeline, unread state, and search.
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
    """Generate a clean, human-readable title from a prompt message or command."""
    if not content or not content.strip():
        return "New Task"

    clean = content.strip()

    # Check for slash commands
    if clean.startswith("/skills"):
        return "Skills & Capabilities"
    elif clean.startswith("/tools"):
        return "Tools & Integrations"
    elif clean.startswith("/plan"):
        rest = clean[5:].strip()
        return f"Plan: {rest[:32]}..." if len(rest) > 32 else (f"Plan: {rest}" if rest else "Strategic Planning")
    elif clean.startswith("/search"):
        rest = clean[7:].strip()
        return f"Search: {rest[:32]}..." if len(rest) > 32 else (f"Search: {rest}" if rest else "Web Search")
    elif clean.startswith("/team") or clean.startswith("/workforce"):
        return "Team Coordination"
    elif clean.startswith("/knowledge") or clean.startswith("/kb"):
        return "Knowledge Consultation"
    elif clean.startswith("/status") or clean.startswith("/health"):
        return "System Status"
    elif clean.startswith("/help"):
        return "Platform Assistance"

    # Clean first line
    first_line = clean.splitlines()[0].strip()
    first_line = re.sub(r"^[#\*\-–—\d\.\s>]+", "", first_line).strip()

    # Strip common conversational prefixes (Italian and English)
    prefixes = [
        r"^(puoi\s+(per\s+favore\s+)?(aiutarmi\s+a\s+|fare\s+|scrivere\s+|creare\s+|analizzare\s+|spiegarmi\s+|trovare\s+|controllare\s+))",
        r"^(vorrei\s+(che\s+tu\s+)?(creassi\s+|scrivessi\s+|facessi\s+|analizzassi\s+|trovassi\s+|sapere\s+))",
        r"^(come\s+(posso\s+|si\s+fa\s+a\s+|posso\s+fare\s+per\s+))",
        r"^(can\s+you\s+(please\s+)?(help\s+me\s+to\s+|write\s+|create\s+|analyze\s+|explain\s+|find\s+|check\s+))",
        r"^(i\s+would\s+like\s+(you\s+to\s+|to\s+))",
        r"^(how\s+(can\s+i\s+|to\s+|do\s+i\s+))",
        r"^(please\s+)",
    ]
    for p in prefixes:
        first_line = re.sub(p, "", first_line, flags=re.IGNORECASE).strip()

    if len(first_line) > 42:
        words = first_line[:40].rsplit(" ", 1)
        first_line = (words[0] if len(words) > 1 else first_line[:40]) + "..."

    return first_line.capitalize() if first_line else "New Task"


from aether.core.sqlite import get_sqlite_connection


class ConversationStore:
    """
    Manages persistent conversations, organizational projects, and UI history within a workspace.
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
            # 1. Projects Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            # 2. Conversations Table
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
                    unread INTEGER DEFAULT 0,
                    pinned INTEGER DEFAULT 0,
                    project_id TEXT DEFAULT NULL
                )
                """
            )

            # Backward-compatibility schema migrations
            try:
                conn.execute("ALTER TABLE conversations ADD COLUMN unread INTEGER DEFAULT 0")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE conversations ADD COLUMN pinned INTEGER DEFAULT 0")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE conversations ADD COLUMN project_id TEXT DEFAULT NULL")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE projects ADD COLUMN github_repository TEXT DEFAULT NULL")
            except Exception:
                pass

            # 3. UI Messages & Activities
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

            # 4. Performance Indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_updated ON conversations(updated_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_pinned ON conversations(pinned DESC, updated_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_project ON conversations(project_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_status ON conversations(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_conv ON conversation_ui_messages(conversation_id, created_at ASC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_content ON conversation_ui_messages(content)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_act_conv ON conversation_activities(conversation_id, created_at ASC)")

    # ---------------------------------------------------------------------------
    # Project CRUD Operations
    # ---------------------------------------------------------------------------

    def create_project(
        self,
        name: str,
        project_id: str | None = None,
        github_repository: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new organizational Project for grouping conversations."""
        clean_name = str(name).strip()
        if not clean_name:
            raise ValueError("Project name cannot be empty.")

        pid = project_id or uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        gh_json = json.dumps(github_repository) if github_repository else None

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, created_at, updated_at, github_repository)
                VALUES (?, ?, ?, ?, ?)
                """,
                (pid, clean_name, now, now, gh_json),
            )

        return {
            "id": pid,
            "name": clean_name,
            "created_at": now,
            "updated_at": now,
            "github_repository": github_repository,
            "conversation_count": 0,
        }

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        """Retrieve project metadata and its associated conversations."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, name, created_at, updated_at, github_repository FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if not row:
                return None

            conv_rows = conn.execute(
                """
                SELECT id, title, team_name, status, created_at, updated_at, last_message, agents, unread, pinned, project_id
                FROM conversations
                WHERE project_id = ?
                ORDER BY pinned DESC, updated_at DESC
                """,
                (project_id,),
            ).fetchall()

        convs = []
        for r in conv_rows:
            agents_list = []
            try:
                agents_list = json.loads(r["agents"] or "[]")
            except Exception:
                pass
            convs.append({
                "id": r["id"],
                "title": r["title"],
                "team_name": r["team_name"],
                "status": r["status"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "last_message": r["last_message"] or "",
                "agents": agents_list,
                "unread": bool(r["unread"] if "unread" in r.keys() else 0),
                "pinned": bool(r["pinned"] if "pinned" in r.keys() else 0),
                "project_id": r["project_id"] if "project_id" in r.keys() else None,
            })

        gh_repo = None
        if "github_repository" in row.keys() and row["github_repository"]:
            try:
                gh_repo = json.loads(row["github_repository"])
            except Exception:
                pass

        return {
            "id": row["id"],
            "name": row["name"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "github_repository": gh_repo,
            "conversation_count": len(convs),
            "conversations": convs,
        }

    def list_projects(self) -> list[dict[str, Any]]:
        """List all projects with their conversation count."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT p.id, p.name, p.created_at, p.updated_at, p.github_repository,
                       COUNT(c.id) as conversation_count
                FROM projects p
                LEFT JOIN conversations c ON c.project_id = p.id AND c.status != 'archived'
                GROUP BY p.id
                ORDER BY p.updated_at DESC
                """
            ).fetchall()

        res = []
        for r in rows:
            gh_repo = None
            if "github_repository" in r.keys() and r["github_repository"]:
                try:
                    gh_repo = json.loads(r["github_repository"])
                except Exception:
                    pass
            res.append({
                "id": r["id"],
                "name": r["name"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "github_repository": gh_repo,
                "conversation_count": int(r["conversation_count"] or 0),
            })
        return res

    def update_project(self, project_id: str, name: str) -> dict[str, Any] | None:
        """Rename an existing project."""
        clean_name = str(name).strip()
        if not clean_name:
            raise ValueError("Project name cannot be empty.")

        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE projects
                SET name = ?, updated_at = ?
                WHERE id = ?
                """,
                (clean_name, now, project_id),
            )
            if cursor.rowcount == 0:
                return None

        return self.get_project(project_id)

    def update_project_github(
        self,
        project_id: str,
        github_repository: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Connect, update, or disconnect (when None) the GitHub repository on a project."""
        gh_json = json.dumps(github_repository) if github_repository else None
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE projects
                SET github_repository = ?, updated_at = ?
                WHERE id = ?
                """,
                (gh_json, now, project_id),
            )
            if cursor.rowcount == 0:
                return None

        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> bool:
        """
        Delete a project. Does NOT delete conversations; unlinks them back to project_id=None.
        """
        with self._get_connection() as conn:
            # 1. Unassign all conversations in this project
            conn.execute(
                "UPDATE conversations SET project_id = NULL WHERE project_id = ?",
                (project_id,),
            )
            # 2. Delete project entry
            cursor = conn.execute(
                "DELETE FROM projects WHERE id = ?",
                (project_id,),
            )
            return cursor.rowcount > 0

    # ---------------------------------------------------------------------------
    # Conversation CRUD Operations
    # ---------------------------------------------------------------------------

    def create(
        self,
        title: str = "New Task",
        team_name: str | None = None,
        conv_id: str | None = None,
        status: str = "active",
        agents: list[str] | None = None,
        pinned: bool = False,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        cid = conv_id or uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        agents_json = json.dumps(agents or [])

        # Validate project existence if project_id specified
        if project_id:
            with self._get_connection() as conn:
                p_exists = conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()
                if not p_exists:
                    raise ValueError(f"Project with id '{project_id}' does not exist.")

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO conversations (id, title, team_name, status, created_at, updated_at, last_message, agents, unread, pinned, project_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    updated_at = excluded.updated_at
                """,
                (cid, title, team_name, status, now, now, "", agents_json, 1 if pinned else 0, project_id),
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
            "pinned": bool(pinned),
            "project_id": project_id,
            "messages": [],
            "activities": [],
        }

    def list(
        self,
        search: str | None = None,
        status: str | None = None,
        include_archived: bool = False,
        project_id: str | None = None,
        pinned: bool | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT id, title, team_name, status, created_at, updated_at, last_message, agents, unread, pinned, project_id FROM conversations WHERE 1=1"
        params: list[Any] = []

        if not include_archived:
            query += " AND status != 'archived'"

        if status:
            query += " AND status = ?"
            params.append(status)

        if project_id is not None:
            if project_id in ("none", "unassigned", ""):
                query += " AND (project_id IS NULL OR project_id = '')"
            else:
                query += " AND project_id = ?"
                params.append(project_id)

        if pinned is not None:
            query += " AND pinned = ?"
            params.append(1 if pinned else 0)

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

        query += " ORDER BY pinned DESC, updated_at DESC LIMIT ?"
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
                "pinned": bool(r["pinned"] if "pinned" in r.keys() else 0),
                "project_id": r["project_id"] if "project_id" in r.keys() else None,
            })
        return results

    def get(self, conv_id: str) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, title, team_name, status, created_at, updated_at, last_message, agents, unread, pinned, project_id FROM conversations WHERE id = ?",
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
            "pinned": bool(row["pinned"] if "pinned" in row.keys() else 0),
            "project_id": row["project_id"] if "project_id" in row.keys() else None,
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
        pinned: bool | None = None,
        project_id: str | None = None,
        clear_project: bool = False,
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat()

        # Validate project_id if provided
        if project_id and not clear_project:
            with self._get_connection() as conn:
                p_exists = conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()
                if not p_exists:
                    raise ValueError(f"Project with id '{project_id}' does not exist.")

        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT title, status, last_message, agents, unread, pinned, project_id FROM conversations WHERE id = ?",
                (conv_id,),
            ).fetchone()
            if not row:
                return None

            new_title = title if title is not None else row["title"]
            new_status = status if status is not None else row["status"]
            new_last = last_message if last_message is not None else row["last_message"]
            new_agents = json.dumps(agents) if agents is not None else row["agents"]
            new_unread = int(unread) if unread is not None else (row["unread"] if "unread" in row.keys() else 0)
            new_pinned = int(pinned) if pinned is not None else (row["pinned"] if "pinned" in row.keys() else 0)

            if clear_project:
                new_project_id = None
            elif project_id is not None:
                new_project_id = project_id
            else:
                new_project_id = row["project_id"] if "project_id" in row.keys() else None

            conn.execute(
                """
                UPDATE conversations
                SET title = ?, status = ?, last_message = ?, agents = ?, unread = ?, pinned = ?, project_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_title, new_status, new_last, new_agents, new_unread, new_pinned, new_project_id, now, conv_id),
            )

        return self.get(conv_id)

    def pin(self, conv_id: str, pinned: bool = True) -> dict[str, Any] | None:
        """Pin or unpin a conversation."""
        return self.update(conv_id, pinned=pinned)

    def assign_to_project(self, conv_id: str, project_id: str | None) -> dict[str, Any] | None:
        """Assign conversation to a project or remove it if project_id is None."""
        if project_id is None:
            return self.update(conv_id, clear_project=True)
        return self.update(conv_id, project_id=project_id)

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
            project_id=existing.get("project_id"),
            pinned=False,
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
        """Permanently remove a conversation and all its cascade children."""
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            return cursor.rowcount > 0

    def add_message(
        self,
        conv_id: str,
        role: str,
        content: str,
        agent_name: str | None = None,
        metadata: dict[str, Any] | None = None,
        msg_id: str | None = None,
    ) -> dict[str, Any]:
        """Record an exchange message in the conversation timeline."""
        mid = msg_id or uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})

        # Compute snippet for last_message preview
        clean_content = content.strip()
        last_snippet = (clean_content[:97] + "...") if len(clean_content) > 100 else clean_content

        with self._get_connection() as conn:
            # Auto-create conversation if missing (e.g. initial draft session)
            row = conn.execute("SELECT title, unread FROM conversations WHERE id = ?", (conv_id,)).fetchone()
            if not row:
                init_title = generate_smart_title(content) if role == "user" else "New Task"
                conn.execute(
                    """
                    INSERT INTO conversations (id, title, team_name, status, created_at, updated_at, last_message, agents, unread, pinned, project_id)
                    VALUES (?, ?, NULL, 'active', ?, ?, '', '[]', 0, 0, NULL)
                    """,
                    (conv_id, init_title, now, now),
                )
                row = conn.execute("SELECT title, unread FROM conversations WHERE id = ?", (conv_id,)).fetchone()

            conn.execute(
                """
                INSERT INTO conversation_ui_messages (id, conversation_id, role, agent_name, content, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (mid, conv_id, role, agent_name, content, now, meta_json),
            )

            # Auto-title conversation if it still has default title
            new_title = None
            if row and (row["title"] in ("New Task", "Nuova Task", "New Conversation") or not row["title"].strip()):
                if role == "user":
                    new_title = generate_smart_title(content)

            unread_val = 1 if role in ("assistant", "system", "agent") else 0

            if new_title:
                conn.execute(
                    """
                    UPDATE conversations
                    SET last_message = ?, updated_at = ?, title = ?, unread = ?
                    WHERE id = ?
                    """,
                    (last_snippet, now, new_title, unread_val, conv_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE conversations
                    SET last_message = ?, updated_at = ?, unread = ?
                    WHERE id = ?
                    """,
                    (last_snippet, now, unread_val, conv_id),
                )

        return {
            "id": mid,
            "conversation_id": conv_id,
            "role": role,
            "agent_name": agent_name,
            "content": content,
            "created_at": now,
            "metadata": metadata or {},
        }

    def delete_message(
        self,
        conv_id: str,
        message_id: str,
        truncate_after: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Delete a message from a conversation and optionally truncate subsequent messages.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            target = conn.execute(
                "SELECT created_at FROM conversation_ui_messages WHERE id = ? AND conversation_id = ?",
                (message_id, conv_id),
            ).fetchone()
            if not target:
                return self.get_messages(conv_id)

            target_created = target["created_at"]

            if truncate_after:
                conn.execute(
                    "DELETE FROM conversation_ui_messages WHERE conversation_id = ? AND created_at >= ?",
                    (conv_id, target_created),
                )
                conn.execute(
                    "DELETE FROM conversation_activities WHERE conversation_id = ? AND created_at >= ?",
                    (conv_id, target_created),
                )
            else:
                conn.execute(
                    "DELETE FROM conversation_ui_messages WHERE id = ?",
                    (message_id,),
                )

            last_msg = conn.execute(
                "SELECT content FROM conversation_ui_messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1",
                (conv_id,),
            ).fetchone()
            snippet = ""
            if last_msg:
                c = last_msg["content"].strip()
                snippet = (c[:97] + "...") if len(c) > 100 else c

            conn.execute(
                "UPDATE conversations SET last_message = ?, updated_at = ? WHERE id = ?",
                (snippet, now, conv_id),
            )

        return self.get_messages(conv_id)

    def edit_message(
        self,
        conv_id: str,
        message_id: str,
        new_content: str,
        truncate_after: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Edit a user message and optionally truncate later messages for conversation forking.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            target = conn.execute(
                "SELECT created_at FROM conversation_ui_messages WHERE id = ? AND conversation_id = ?",
                (message_id, conv_id),
            ).fetchone()
            if not target:
                raise ValueError(f"Message '{message_id}' not found in conversation '{conv_id}'.")

            target_created = target["created_at"]

            if truncate_after:
                conn.execute(
                    "DELETE FROM conversation_ui_messages WHERE conversation_id = ? AND created_at > ?",
                    (conv_id, target_created),
                )
                conn.execute(
                    "DELETE FROM conversation_activities WHERE conversation_id = ? AND created_at > ?",
                    (conv_id, target_created),
                )

            conn.execute(
                "UPDATE conversation_ui_messages SET content = ? WHERE id = ?",
                (new_content, message_id),
            )

            last_msg = conn.execute(
                "SELECT content FROM conversation_ui_messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1",
                (conv_id,),
            ).fetchone()
            snippet = ""
            if last_msg:
                c = last_msg["content"].strip()
                snippet = (c[:97] + "...") if len(c) > 100 else c

            conn.execute(
                "UPDATE conversations SET last_message = ?, updated_at = ? WHERE id = ?",
                (snippet, now, conv_id),
            )

        return self.get_messages(conv_id)

    def add_activity(
        self,
        conv_id: str,
        agent: str,
        activity_type: str,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
        act_id: str | None = None,
    ) -> dict[str, Any]:
        """Record an agent runtime event / tool action in the activity timeline."""
        aid = act_id or uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO conversation_activities (id, conversation_id, agent, activity_type, message, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (aid, conv_id, agent, activity_type, message or "", meta_json, now),
            )

        return {
            "id": aid,
            "conversation_id": conv_id,
            "agent": agent,
            "type": activity_type,
            "message": message or "",
            "metadata": metadata or {},
            "timestamp": now,
        }
