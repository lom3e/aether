import json
import sqlite3
from typing import Any
from pathlib import Path

from aether.core.execution import Message, ToolCall
from aether.memory.conversation import ConversationMemory


class PersistentConversationMemory(ConversationMemory):
    """
    Persistent SQLite-backed short-term conversation memory.
    Isolates messages by agent_id and session_id.
    """

    def __init__(self, db_path: str | Path, agent_id: str) -> None:
        super().__init__()
        self.db_path = str(db_path)
        if self.db_path == ":memory:":
            import uuid
            self.db_path = f"file:memdb_conv_{uuid.uuid4().hex}?mode=memory&cache=shared"
            
        self.agent_id = agent_id
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, uri=self.db_path.startswith("file:"))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT,
                    tool_calls TEXT,
                    timestamp REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_session ON conversation_history(agent_id, session_id)"
            )

    def get_messages(self, session_id: str) -> list[Message]:
        """
        Retrieve message history for a session from SQLite.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT role, content, tool_calls FROM conversation_history WHERE agent_id = ? AND session_id = ? ORDER BY id ASC",
                (self.agent_id, session_id)
            ).fetchall()

        messages = []
        for row in rows:
            tool_calls = None
            if row["tool_calls"]:
                try:
                    tc_data = json.loads(row["tool_calls"])
                    tool_calls = []
                    for tc in tc_data:
                        tool_calls.append(
                            ToolCall(call_id=tc["call_id"], tool_name=tc["tool_name"], arguments=tc["arguments"])
                        )
                except Exception:
                    pass
            
            messages.append(Message(
                role=row["role"],
                content=row["content"],
                tool_calls=tool_calls
            ))
        return messages

    def add_message(self, session_id: str, message: Message) -> None:
        """
        Add a message to the history of a session in SQLite.
        """
        import time
        tool_calls_json = None
        if message.tool_calls:
            tc_list = []
            for tc in message.tool_calls:
                tc_list.append({
                    "call_id": tc.call_id,
                    "tool_name": tc.tool_name,
                    "arguments": tc.arguments
                })
            tool_calls_json = json.dumps(tc_list)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO conversation_history (agent_id, session_id, role, content, tool_calls, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (self.agent_id, session_id, message.role, message.content, tool_calls_json, time.time())
            )

    def set_messages(self, session_id: str, messages: list[Message]) -> None:
        """
        Set or overwrite message history for a session in SQLite.
        """
        with self._get_connection() as conn:
            # We wrap in a transaction to ensure atomic replacement
            conn.execute("BEGIN TRANSACTION")
            try:
                conn.execute(
                    "DELETE FROM conversation_history WHERE agent_id = ? AND session_id = ?",
                    (self.agent_id, session_id)
                )
                
                import time
                timestamp = time.time()
                for message in messages:
                    tool_calls_json = None
                    if message.tool_calls:
                        tc_list = []
                        for tc in message.tool_calls:
                            tc_list.append({
                                "call_id": tc.call_id,
                                "tool_name": tc.tool_name,
                                "arguments": tc.arguments
                            })
                        tool_calls_json = json.dumps(tc_list)
                    
                    conn.execute(
                        """
                        INSERT INTO conversation_history (agent_id, session_id, role, content, tool_calls, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (self.agent_id, session_id, message.role, message.content, tool_calls_json, timestamp)
                    )
                    timestamp += 0.000001 # to preserve strict chronological insertion order if needed
                
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def clear(self, session_id: str) -> None:
        """
        Clear message history for a session in SQLite.
        """
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM conversation_history WHERE agent_id = ? AND session_id = ?",
                (self.agent_id, session_id)
            )
