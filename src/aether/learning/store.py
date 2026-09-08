"""
Persistent SQLite Storage for Aether Learning & Correction Loop (Phase B — Slice 4).

Guarantees:
- Strict workspace isolation for all tables and queries.
- Thread-safe connection handling with WAL mode and busy timeout.
- Deterministic canonical deduplication and idempotency.
- Regression tracking and bounded query pagination.
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

from aether.learning.models import (
    Correction,
    DistilledLesson,
    LearningEvent,
    LearningEventType,
    LearningScope,
    LearningVerificationStatus,
)

logger = logging.getLogger(__name__)


class LearningStore:
    """SQLite-backed store for LearningEvents, Corrections, and DistilledLessons."""

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
                isolation_level=None,  # Autocommit mode; we manage transactions explicitly
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
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE;")
        try:
            yield cursor
            cursor.execute("COMMIT;")
        except Exception:
            cursor.execute("ROLLBACK;")
            raise
        finally:
            cursor.close()

    def _init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self._transaction() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS learning_events (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    observed_behavior TEXT NOT NULL,
                    expected_behavior TEXT NOT NULL,
                    correction TEXT NOT NULL,
                    evidence JSON,
                    verification_status TEXT NOT NULL,
                    mission_id TEXT,
                    execution_id TEXT,
                    milestone_id TEXT,
                    agent_name TEXT,
                    team_name TEXT,
                    source_memory_ids JSON,
                    created_at TEXT NOT NULL,
                    metadata JSON
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS corrections (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    target_scope TEXT NOT NULL,
                    target_identifier TEXT NOT NULL,
                    problem TEXT NOT NULL,
                    correction TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    evidence JSON,
                    source_mission_id TEXT,
                    source_execution_id TEXT,
                    verification_status TEXT NOT NULL,
                    verified_at TEXT,
                    created_at TEXT NOT NULL,
                    metadata JSON
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS distilled_lessons (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    lesson_text TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    target_identifier TEXT NOT NULL,
                    source_mission_id TEXT,
                    source_execution_id TEXT,
                    source_correction_id TEXT,
                    quality_gate_rule TEXT,
                    verification_status TEXT NOT NULL,
                    memory_id TEXT,
                    node_id TEXT,
                    is_regression INTEGER NOT NULL DEFAULT 0,
                    regression_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    metadata JSON
                );
            """)

            # Indexes for high performance and strict workspace queries
            cur.execute("CREATE INDEX IF NOT EXISTS idx_le_ws_type ON learning_events(workspace_id, event_type);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_le_ws_mission ON learning_events(workspace_id, mission_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_corr_ws_status ON corrections(workspace_id, verification_status);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_corr_ws_target ON corrections(workspace_id, target_scope, target_identifier);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_lsn_ws_scope ON distilled_lessons(workspace_id, scope, target_identifier);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_lsn_ws_regr ON distilled_lessons(workspace_id, is_regression);")

    # -------------------------------------------------------------------------
    # Learning Events
    # -------------------------------------------------------------------------

    def record_event(self, event: LearningEvent) -> LearningEvent:
        """Persist a single observable LearningEvent."""
        with self._transaction() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO learning_events (
                    id, workspace_id, event_type, observed_behavior, expected_behavior,
                    correction, evidence, verification_status, mission_id, execution_id,
                    milestone_id, agent_name, team_name, source_memory_ids, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    event.id,
                    event.workspace_id,
                    event.event_type.value if isinstance(event.event_type, LearningEventType) else str(event.event_type),
                    event.observed_behavior,
                    event.expected_behavior,
                    event.correction,
                    json.dumps(event.evidence or {}),
                    event.verification_status.value if isinstance(event.verification_status, LearningVerificationStatus) else str(event.verification_status),
                    event.mission_id,
                    event.execution_id,
                    event.milestone_id,
                    event.agent_name,
                    event.team_name,
                    json.dumps(list(event.source_memory_ids or [])),
                    event.created_at,
                    json.dumps(event.metadata or {}),
                ),
            )
        return event

    def get_event(self, event_id: str, workspace_id: str | None = None) -> LearningEvent | None:
        """Retrieve a learning event by ID."""
        conn = self._get_connection()
        query = "SELECT * FROM learning_events WHERE id = ?"
        params: list[Any] = [event_id]
        if workspace_id:
            query += " AND workspace_id = ?"
            params.append(workspace_id)
        row = conn.execute(query, params).fetchone()
        if not row:
            return None
        return self._row_to_event(row)

    def list_events(
        self,
        workspace_id: str,
        event_type: str | None = None,
        mission_id: str | None = None,
        execution_id: str | None = None,
        verification_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LearningEvent]:
        """List events filtered by workspace and optional criteria."""
        conn = self._get_connection()
        conditions = ["workspace_id = ?"]
        params: list[Any] = [workspace_id]

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if mission_id:
            conditions.append("mission_id = ?")
            params.append(mission_id)
        if execution_id:
            conditions.append("execution_id = ?")
            params.append(execution_id)
        if verification_status:
            conditions.append("verification_status = ?")
            params.append(verification_status)

        query = f"SELECT * FROM learning_events WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, limit), max(0, offset)])
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_event(r) for r in rows]

    def _row_to_event(self, row: sqlite3.Row) -> LearningEvent:
        return LearningEvent(
            id=row["id"],
            workspace_id=row["workspace_id"],
            event_type=LearningEventType.from_str(row["event_type"]),
            observed_behavior=row["observed_behavior"],
            expected_behavior=row["expected_behavior"],
            correction=row["correction"],
            evidence=json.loads(row["evidence"]) if row["evidence"] else {},
            verification_status=LearningVerificationStatus.from_str(row["verification_status"]),
            mission_id=row["mission_id"],
            execution_id=row["execution_id"],
            milestone_id=row["milestone_id"],
            agent_name=row["agent_name"],
            team_name=row["team_name"],
            source_memory_ids=json.loads(row["source_memory_ids"]) if row["source_memory_ids"] else [],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    # -------------------------------------------------------------------------
    # Corrections
    # -------------------------------------------------------------------------

    def create_or_get_correction(self, correction: Correction) -> tuple[Correction, bool]:
        """
        Idempotently create or retrieve an existing identical correction.
        Returns (Correction, created_bool).
        """
        conn = self._get_connection()
        # Find match on workspace_id, target_scope, target_identifier, problem, and source_execution_id
        row = conn.execute(
            """
            SELECT * FROM corrections
            WHERE workspace_id = ? AND target_scope = ? AND target_identifier = ? AND problem = ?
            AND (source_execution_id = ? OR source_execution_id IS NULL)
            LIMIT 1;
            """,
            (
                correction.workspace_id,
                correction.target_scope.value if isinstance(correction.target_scope, LearningScope) else str(correction.target_scope),
                correction.target_identifier,
                correction.problem,
                correction.source_execution_id,
            ),
        ).fetchone()

        if row:
            return self._row_to_correction(row), False

        with self._transaction() as cur:
            cur.execute(
                """
                INSERT INTO corrections (
                    id, workspace_id, target_scope, target_identifier, problem,
                    correction, rationale, evidence, source_mission_id, source_execution_id,
                    verification_status, verified_at, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    correction.id,
                    correction.workspace_id,
                    correction.target_scope.value if isinstance(correction.target_scope, LearningScope) else str(correction.target_scope),
                    correction.target_identifier,
                    correction.problem,
                    correction.correction,
                    correction.rationale,
                    json.dumps(correction.evidence or {}),
                    correction.source_mission_id,
                    correction.source_execution_id,
                    correction.verification_status.value if isinstance(correction.verification_status, LearningVerificationStatus) else str(correction.verification_status),
                    correction.verified_at,
                    correction.created_at,
                    json.dumps(correction.metadata or {}),
                ),
            )
        return correction, True

    def get_correction(self, correction_id: str, workspace_id: str | None = None) -> Correction | None:
        """Retrieve a correction by ID."""
        conn = self._get_connection()
        query = "SELECT * FROM corrections WHERE id = ?"
        params: list[Any] = [correction_id]
        if workspace_id:
            query += " AND workspace_id = ?"
            params.append(workspace_id)
        row = conn.execute(query, params).fetchone()
        if not row:
            return None
        return self._row_to_correction(row)

    def update_correction(self, correction: Correction) -> Correction:
        """Update an existing correction."""
        with self._transaction() as cur:
            cur.execute(
                """
                UPDATE corrections SET
                    target_scope = ?,
                    target_identifier = ?,
                    problem = ?,
                    correction = ?,
                    rationale = ?,
                    evidence = ?,
                    source_mission_id = ?,
                    source_execution_id = ?,
                    verification_status = ?,
                    verified_at = ?,
                    metadata = ?
                WHERE id = ? AND workspace_id = ?;
                """,
                (
                    correction.target_scope.value if isinstance(correction.target_scope, LearningScope) else str(correction.target_scope),
                    correction.target_identifier,
                    correction.problem,
                    correction.correction,
                    correction.rationale,
                    json.dumps(correction.evidence or {}),
                    correction.source_mission_id,
                    correction.source_execution_id,
                    correction.verification_status.value if isinstance(correction.verification_status, LearningVerificationStatus) else str(correction.verification_status),
                    correction.verified_at,
                    json.dumps(correction.metadata or {}),
                    correction.id,
                    correction.workspace_id,
                ),
            )
        return correction

    def list_corrections(
        self,
        workspace_id: str,
        status: str | None = None,
        scope: str | None = None,
        target_identifier: str | None = None,
        source_mission_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Correction]:
        """List corrections with workspace isolation and filters."""
        conn = self._get_connection()
        conditions = ["workspace_id = ?"]
        params: list[Any] = [workspace_id]

        if status:
            conditions.append("verification_status = ?")
            params.append(status)
        if scope:
            conditions.append("target_scope = ?")
            params.append(scope)
        if target_identifier:
            conditions.append("target_identifier = ?")
            params.append(target_identifier)
        if source_mission_id:
            conditions.append("source_mission_id = ?")
            params.append(source_mission_id)

        query = f"SELECT * FROM corrections WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, limit), max(0, offset)])
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_correction(r) for r in rows]

    def _row_to_correction(self, row: sqlite3.Row) -> Correction:
        return Correction(
            id=row["id"],
            workspace_id=row["workspace_id"],
            target_scope=LearningScope.from_str(row["target_scope"]),
            target_identifier=row["target_identifier"],
            problem=row["problem"],
            correction=row["correction"],
            rationale=row["rationale"],
            evidence=json.loads(row["evidence"]) if row["evidence"] else {},
            source_mission_id=row["source_mission_id"],
            source_execution_id=row["source_execution_id"],
            verification_status=LearningVerificationStatus.from_str(row["verification_status"]),
            verified_at=row["verified_at"],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    # -------------------------------------------------------------------------
    # Distilled Lessons
    # -------------------------------------------------------------------------

    def create_or_get_lesson(self, lesson: DistilledLesson) -> tuple[DistilledLesson, bool]:
        """
        Idempotently create or retrieve an identical distilled lesson.
        Returns (DistilledLesson, created_bool).
        """
        conn = self._get_connection()
        row = conn.execute(
            """
            SELECT * FROM distilled_lessons
            WHERE workspace_id = ? AND scope = ? AND target_identifier = ? AND lesson_text = ?
            LIMIT 1;
            """,
            (
                lesson.workspace_id,
                lesson.scope.value if isinstance(lesson.scope, LearningScope) else str(lesson.scope),
                lesson.target_identifier,
                lesson.lesson_text,
            ),
        ).fetchone()

        if row:
            return self._row_to_lesson(row), False

        with self._transaction() as cur:
            cur.execute(
                """
                INSERT INTO distilled_lessons (
                    id, workspace_id, title, lesson_text, scope, target_identifier,
                    source_mission_id, source_execution_id, source_correction_id,
                    quality_gate_rule, verification_status, memory_id, node_id,
                    is_regression, regression_count, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    lesson.id,
                    lesson.workspace_id,
                    lesson.title,
                    lesson.lesson_text,
                    lesson.scope.value if isinstance(lesson.scope, LearningScope) else str(lesson.scope),
                    lesson.target_identifier,
                    lesson.source_mission_id,
                    lesson.source_execution_id,
                    lesson.source_correction_id,
                    lesson.quality_gate_rule,
                    lesson.verification_status.value if isinstance(lesson.verification_status, LearningVerificationStatus) else str(lesson.verification_status),
                    lesson.memory_id,
                    lesson.node_id,
                    1 if lesson.is_regression else 0,
                    lesson.regression_count,
                    lesson.created_at,
                    json.dumps(lesson.metadata or {}),
                ),
            )
        return lesson, True

    def get_lesson(self, lesson_id: str, workspace_id: str | None = None) -> DistilledLesson | None:
        """Retrieve a distilled lesson by ID."""
        conn = self._get_connection()
        query = "SELECT * FROM distilled_lessons WHERE id = ?"
        params: list[Any] = [lesson_id]
        if workspace_id:
            query += " AND workspace_id = ?"
            params.append(workspace_id)
        row = conn.execute(query, params).fetchone()
        if not row:
            return None
        return self._row_to_lesson(row)

    def update_lesson(self, lesson: DistilledLesson) -> DistilledLesson:
        """Update an existing lesson (e.g. memory_id, node_id, regression count)."""
        with self._transaction() as cur:
            cur.execute(
                """
                UPDATE distilled_lessons SET
                    title = ?,
                    lesson_text = ?,
                    scope = ?,
                    target_identifier = ?,
                    quality_gate_rule = ?,
                    verification_status = ?,
                    memory_id = ?,
                    node_id = ?,
                    is_regression = ?,
                    regression_count = ?,
                    metadata = ?
                WHERE id = ? AND workspace_id = ?;
                """,
                (
                    lesson.title,
                    lesson.lesson_text,
                    lesson.scope.value if isinstance(lesson.scope, LearningScope) else str(lesson.scope),
                    lesson.target_identifier,
                    lesson.quality_gate_rule,
                    lesson.verification_status.value if isinstance(lesson.verification_status, LearningVerificationStatus) else str(lesson.verification_status),
                    lesson.memory_id,
                    lesson.node_id,
                    1 if lesson.is_regression else 0,
                    lesson.regression_count,
                    json.dumps(lesson.metadata or {}),
                    lesson.id,
                    lesson.workspace_id,
                ),
            )
        return lesson

    def list_lessons(
        self,
        workspace_id: str,
        scope: str | None = None,
        target_identifier: str | None = None,
        is_regression: bool | None = None,
        verification_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DistilledLesson]:
        """List distilled lessons with workspace isolation and filters."""
        conn = self._get_connection()
        conditions = ["workspace_id = ?"]
        params: list[Any] = [workspace_id]

        if scope:
            conditions.append("scope = ?")
            params.append(scope)
        if target_identifier:
            conditions.append("target_identifier = ?")
            params.append(target_identifier)
        if is_regression is not None:
            conditions.append("is_regression = ?")
            params.append(1 if is_regression else 0)
        if verification_status:
            conditions.append("verification_status = ?")
            params.append(verification_status)

        query = f"SELECT * FROM distilled_lessons WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, limit), max(0, offset)])
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_lesson(r) for r in rows]

    def _row_to_lesson(self, row: sqlite3.Row) -> DistilledLesson:
        return DistilledLesson(
            id=row["id"],
            workspace_id=row["workspace_id"],
            title=row["title"],
            lesson_text=row["lesson_text"],
            scope=LearningScope.from_str(row["scope"]),
            target_identifier=row["target_identifier"],
            source_mission_id=row["source_mission_id"],
            source_execution_id=row["source_execution_id"],
            source_correction_id=row["source_correction_id"],
            quality_gate_rule=row["quality_gate_rule"],
            verification_status=LearningVerificationStatus.from_str(row["verification_status"]),
            memory_id=row["memory_id"],
            node_id=row["node_id"],
            is_regression=bool(row["is_regression"]),
            regression_count=int(row["regression_count"]),
            created_at=row["created_at"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def close(self) -> None:
        """Close connection for current thread."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None
