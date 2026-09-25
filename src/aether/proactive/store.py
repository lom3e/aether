"""Persistent SQLite store for Watchers, Proactive Suggestions, and Watcher Events."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, List, Optional
from datetime import datetime, timezone

from aether.proactive.models import (
    ProactiveSuggestion,
    SuggestionCategory,
    SuggestionPriority,
    SuggestionStatus,
    Watcher,
    WatcherEvent,
    WatcherStatus,
    WatcherType,
)


class ProactiveStore:
    """Manages persistence for Ambient Watchers and Proactive Intelligence Suggestions."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS watchers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    watcher_type TEXT NOT NULL,
                    target TEXT NOT NULL,
                    condition_expression TEXT NOT NULL,
                    last_state TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    action_args TEXT NOT NULL,
                    auto_trigger INTEGER NOT NULL DEFAULT 0,
                    interval_seconds INTEGER NOT NULL DEFAULT 60,
                    status TEXT NOT NULL,
                    last_checked_at TEXT NOT NULL,
                    last_triggered_at TEXT,
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS proactive_suggestions (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    proposed_action_id TEXT NOT NULL,
                    proposed_action_args TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    metadata TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS watcher_events (
                    id TEXT PRIMARY KEY,
                    watcher_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details TEXT NOT NULL,
                    action_executed INTEGER NOT NULL DEFAULT 0,
                    action_result TEXT,
                    timestamp TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_watchers_status ON watchers(status);
                CREATE INDEX IF NOT EXISTS idx_suggestions_status ON proactive_suggestions(status);
                CREATE INDEX IF NOT EXISTS idx_watcher_events_wid ON watcher_events(watcher_id);
                """
            )

    # -------------------------------------------------------------------------
    # Watchers CRUD
    # -------------------------------------------------------------------------

    def save_watcher(self, watcher: Watcher) -> Watcher:
        """Create or update a watcher definition."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO watchers (
                    id, name, description, watcher_type, target,
                    condition_expression, last_state, action_id, action_args,
                    auto_trigger, interval_seconds, status,
                    last_checked_at, last_triggered_at, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    watcher.id,
                    watcher.name,
                    watcher.description,
                    watcher.watcher_type.value if isinstance(watcher.watcher_type, WatcherType) else watcher.watcher_type,
                    watcher.target,
                    watcher.condition_expression,
                    json.dumps(watcher.last_state),
                    watcher.action_id,
                    json.dumps(watcher.action_args),
                    1 if watcher.auto_trigger else 0,
                    watcher.interval_seconds,
                    watcher.status.value if isinstance(watcher.status, WatcherStatus) else watcher.status,
                    watcher.last_checked_at,
                    watcher.last_triggered_at,
                    watcher.created_at,
                    json.dumps(watcher.metadata),
                ),
            )
        return watcher

    def get_watcher(self, watcher_id: str) -> Optional[Watcher]:
        """Fetch watcher by ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM watchers WHERE id = ?", (watcher_id,)).fetchone()
            if not row:
                return None
            return self._row_to_watcher(row)

    def list_watchers(
        self, status: Optional[str] = None, watcher_type: Optional[str] = None
    ) -> List[Watcher]:
        """List registered watchers with optional filtering."""
        query = "SELECT * FROM watchers WHERE 1=1"
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if watcher_type:
            query += " AND watcher_type = ?"
            params.append(watcher_type)
        query += " ORDER BY created_at DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_watcher(r) for r in rows]

    def delete_watcher(self, watcher_id: str) -> bool:
        """Delete a watcher by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM watchers WHERE id = ?", (watcher_id,))
            return cursor.rowcount > 0

    def update_watcher_status(
        self, watcher_id: str, status: WatcherStatus
    ) -> Optional[Watcher]:
        """Update operational status of a watcher."""
        w = self.get_watcher(watcher_id)
        if not w:
            return None
        w.status = status
        return self.save_watcher(w)

    def _row_to_watcher(self, row: sqlite3.Row) -> Watcher:
        return Watcher(
            id=row["id"],
            name=row["name"] or "",
            description=row["description"] or "",
            watcher_type=WatcherType(row["watcher_type"] or "file_change"),
            target=row["target"] or "",
            condition_expression=row["condition_expression"] or "modified",
            last_state=json.loads(row["last_state"] or "{}"),
            action_id=row["action_id"] or "",
            action_args=json.loads(row["action_args"] or "{}"),
            auto_trigger=bool(row["auto_trigger"]),
            interval_seconds=row["interval_seconds"] or 60,
            status=WatcherStatus(row["status"] or "active"),
            last_checked_at=row["last_checked_at"] or "",
            last_triggered_at=row["last_triggered_at"],
            created_at=row["created_at"] or "",
            metadata=json.loads(row["metadata"] or "{}"),
        )

    # -------------------------------------------------------------------------
    # Suggestions CRUD
    # -------------------------------------------------------------------------

    def save_suggestion(self, suggestion: ProactiveSuggestion) -> ProactiveSuggestion:
        """Create or update a proactive suggestion."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO proactive_suggestions (
                    id, category, title, description,
                    proposed_action_id, proposed_action_args, evidence,
                    priority, status, created_at, resolved_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    suggestion.id,
                    suggestion.category.value if isinstance(suggestion.category, SuggestionCategory) else suggestion.category,
                    suggestion.title,
                    suggestion.description,
                    suggestion.proposed_action_id,
                    json.dumps(suggestion.proposed_action_args),
                    json.dumps(suggestion.evidence),
                    suggestion.priority.value if isinstance(suggestion.priority, SuggestionPriority) else suggestion.priority,
                    suggestion.status.value if isinstance(suggestion.status, SuggestionStatus) else suggestion.status,
                    suggestion.created_at,
                    suggestion.resolved_at,
                    json.dumps(suggestion.metadata),
                ),
            )
        return suggestion

    def get_suggestion(self, suggestion_id: str) -> Optional[ProactiveSuggestion]:
        """Fetch a proactive suggestion by ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM proactive_suggestions WHERE id = ?", (suggestion_id,)).fetchone()
            if not row:
                return None
            return self._row_to_suggestion(row)

    def list_suggestions(
        self, status: Optional[str] = None, category: Optional[str] = None
    ) -> List[ProactiveSuggestion]:
        """List suggestions with optional filtering."""
        query = "SELECT * FROM proactive_suggestions WHERE 1=1"
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY created_at DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_suggestion(r) for r in rows]

    def update_suggestion_status(
        self, suggestion_id: str, status: SuggestionStatus
    ) -> Optional[ProactiveSuggestion]:
        """Update lifecycle status of a proactive suggestion."""
        s = self.get_suggestion(suggestion_id)
        if not s:
            return None
        s.status = status
        if status in (SuggestionStatus.ACCEPTED, SuggestionStatus.DISMISSED, SuggestionStatus.APPLIED):
            s.resolved_at = datetime.now(timezone.utc).isoformat()
        return self.save_suggestion(s)

    def _row_to_suggestion(self, row: sqlite3.Row) -> ProactiveSuggestion:
        return ProactiveSuggestion(
            id=row["id"],
            category=SuggestionCategory(row["category"] or "automation_discovery"),
            title=row["title"] or "",
            description=row["description"] or "",
            proposed_action_id=row["proposed_action_id"] or "",
            proposed_action_args=json.loads(row["proposed_action_args"] or "{}"),
            evidence=json.loads(row["evidence"] or "{}"),
            priority=SuggestionPriority(row["priority"] or "medium"),
            status=SuggestionStatus(row["status"] or "pending"),
            created_at=row["created_at"] or "",
            resolved_at=row["resolved_at"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    # -------------------------------------------------------------------------
    # Watcher Events CRUD
    # -------------------------------------------------------------------------

    def save_event(self, event: WatcherEvent) -> WatcherEvent:
        """Record a watcher check or trigger event."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO watcher_events (
                    id, watcher_id, event_type, details,
                    action_executed, action_result, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.watcher_id,
                    event.event_type,
                    json.dumps(event.details),
                    1 if event.action_executed else 0,
                    json.dumps(event.action_result) if event.action_result else None,
                    event.timestamp,
                ),
            )
        return event

    def list_events(
        self, watcher_id: Optional[str] = None, limit: int = 50
    ) -> List[WatcherEvent]:
        """List historical watcher events."""
        query = "SELECT * FROM watcher_events WHERE 1=1"
        params: List[Any] = []
        if watcher_id:
            query += " AND watcher_id = ?"
            params.append(watcher_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [
                WatcherEvent(
                    id=r["id"],
                    watcher_id=r["watcher_id"] or "",
                    event_type=r["event_type"] or "check",
                    details=json.loads(r["details"] or "{}"),
                    action_executed=bool(r["action_executed"]),
                    action_result=json.loads(r["action_result"]) if r["action_result"] else None,
                    timestamp=r["timestamp"] or "",
                )
                for r in rows
            ]
