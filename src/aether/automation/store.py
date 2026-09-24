"""
AutomationStore — SQLite persistence for Automation Workflows and Execution Run Logs.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Generator

from aether.automation.models import (
    AutomationDefinition,
    AutomationRunRecord,
    AutomationSuggestion,
    OutputDestination,
    PipelineStep,
    RunStatus,
    SuggestionStatus,
    TriggerConfig,
)
from aether.core.sqlite import get_sqlite_connection, sqlite_connection


class AutomationStore:
    """Manages persistent automation workflows and run execution history."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._is_memory = self.db_path == ":memory:" or "mode=memory" in self.db_path
        if self.db_path == ":memory:":
            self.db_path = f"file:memdb_auto_{uuid.uuid4().hex}?mode=memory&cache=shared"
        self._keepalive_conn: sqlite3.Connection | None = (
            get_sqlite_connection(self.db_path) if self._is_memory else None
        )
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        with sqlite_connection(self.db_path) as conn:
            yield conn


    def _init_db(self) -> None:
        with self._get_connection() as conn:
            # 1. Automations Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS automations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    team_name TEXT,
                    trigger_json TEXT NOT NULL,
                    steps_json TEXT NOT NULL DEFAULT '[]',
                    output_destination_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_run_at TEXT,
                    last_run_status TEXT,
                    next_run_at TEXT,
                    is_draft INTEGER NOT NULL DEFAULT 0,
                    requires_approval INTEGER NOT NULL DEFAULT 0,
                    human_schedule TEXT,
                    metadata_json TEXT DEFAULT '{}'
                );
                """
            )
            # Check existing columns in automations for forward migration
            cursor = conn.execute("PRAGMA table_info(automations);")
            columns = {row[1] for row in cursor.fetchall()}
            if "is_draft" not in columns:
                conn.execute("ALTER TABLE automations ADD COLUMN is_draft INTEGER NOT NULL DEFAULT 0;")
            if "requires_approval" not in columns:
                conn.execute("ALTER TABLE automations ADD COLUMN requires_approval INTEGER NOT NULL DEFAULT 0;")
            if "human_schedule" not in columns:
                conn.execute("ALTER TABLE automations ADD COLUMN human_schedule TEXT;")
            if "metadata_json" not in columns:
                conn.execute("ALTER TABLE automations ADD COLUMN metadata_json TEXT DEFAULT '{}';")

            # 2. Automation Runs History Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS automation_runs (
                    run_id TEXT PRIMARY KEY,
                    automation_id TEXT NOT NULL,
                    automation_name TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    duration_seconds REAL,
                    input_payload_json TEXT NOT NULL DEFAULT '{}',
                    output_result TEXT,
                    error TEXT,
                    step_runs_json TEXT NOT NULL DEFAULT '[]',
                    FOREIGN KEY (automation_id) REFERENCES automations(id) ON DELETE CASCADE
                );
                """
            )
            # Indices for quick lookup
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_automation_runs_auto_id ON automation_runs(automation_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_automation_runs_started ON automation_runs(started_at DESC);"
            )

            # 3. Automation Suggestions Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS automation_suggestions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    rationale TEXT NOT NULL DEFAULT '',
                    evidence_count INTEGER NOT NULL DEFAULT 1,
                    evidence_summary TEXT NOT NULL DEFAULT '',
                    trigger_json TEXT NOT NULL,
                    steps_json TEXT NOT NULL DEFAULT '[]',
                    output_destination_json TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    automation_id TEXT
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_suggestions_status ON automation_suggestions(status);"
            )

    def list_automations(self) -> list[AutomationDefinition]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, name, description, enabled, team_name, trigger_json, steps_json, "
                "output_destination_json, created_at, updated_at, last_run_at, last_run_status, next_run_at, "
                "is_draft, requires_approval, human_schedule, metadata_json "
                "FROM automations ORDER BY created_at ASC;"
            )
            rows = cursor.fetchall()

        res: list[AutomationDefinition] = []
        for r in rows:
            trigger_data = json.loads(r[5]) if r[5] else {}
            steps_data = json.loads(r[6]) if r[6] else []
            out_data = json.loads(r[7]) if r[7] else None
            meta_data = json.loads(r[16]) if len(r) > 16 and r[16] else {}

            res.append(
                AutomationDefinition(
                    id=r[0],
                    name=r[1],
                    description=r[2],
                    enabled=bool(r[3]),
                    team_name=r[4],
                    trigger=TriggerConfig.from_dict(trigger_data),
                    steps=[PipelineStep.from_dict(s) for s in steps_data],
                    output_destination=OutputDestination.from_dict(out_data) if out_data else None,
                    created_at=r[8],
                    updated_at=r[9],
                    last_run_at=r[10],
                    last_run_status=r[11],
                    next_run_at=r[12],
                    is_draft=bool(r[13]) if len(r) > 13 else False,
                    requires_approval=bool(r[14]) if len(r) > 14 else False,
                    human_schedule=r[15] if len(r) > 15 else None,
                    metadata=meta_data,
                )
            )
        return res

    def get_automation(self, automation_id: str) -> AutomationDefinition | None:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, name, description, enabled, team_name, trigger_json, steps_json, "
                "output_destination_json, created_at, updated_at, last_run_at, last_run_status, next_run_at, "
                "is_draft, requires_approval, human_schedule, metadata_json "
                "FROM automations WHERE id = ?;",
                (automation_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        trigger_data = json.loads(row[5]) if row[5] else {}
        steps_data = json.loads(row[6]) if row[6] else []
        out_data = json.loads(row[7]) if row[7] else None
        meta_data = json.loads(row[16]) if len(row) > 16 and row[16] else {}

        return AutomationDefinition(
            id=row[0],
            name=row[1],
            description=row[2],
            enabled=bool(row[3]),
            team_name=row[4],
            trigger=TriggerConfig.from_dict(trigger_data),
            steps=[PipelineStep.from_dict(s) for s in steps_data],
            output_destination=OutputDestination.from_dict(out_data) if out_data else None,
            created_at=row[8],
            updated_at=row[9],
            last_run_at=row[10],
            last_run_status=row[11],
            next_run_at=row[12],
            is_draft=bool(row[13]) if len(row) > 13 else False,
            requires_approval=bool(row[14]) if len(row) > 14 else False,
            human_schedule=row[15] if len(row) > 15 else None,
            metadata=meta_data,
        )

    def save_automation(self, auto: AutomationDefinition) -> AutomationDefinition:
        now = datetime.now(timezone.utc).isoformat()
        if not auto.created_at:
            auto.created_at = now
        auto.updated_at = now

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO automations (
                    id, name, description, enabled, team_name, trigger_json, steps_json,
                    output_destination_json, created_at, updated_at, last_run_at, last_run_status, next_run_at,
                    is_draft, requires_approval, human_schedule, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    enabled = excluded.enabled,
                    team_name = excluded.team_name,
                    trigger_json = excluded.trigger_json,
                    steps_json = excluded.steps_json,
                    output_destination_json = excluded.output_destination_json,
                    updated_at = excluded.updated_at,
                    last_run_at = excluded.last_run_at,
                    last_run_status = excluded.last_run_status,
                    next_run_at = excluded.next_run_at,
                    is_draft = excluded.is_draft,
                    requires_approval = excluded.requires_approval,
                    human_schedule = excluded.human_schedule,
                    metadata_json = excluded.metadata_json;
                """,
                (
                    auto.id,
                    auto.name,
                    auto.description,
                    1 if auto.enabled else 0,
                    auto.team_name,
                    json.dumps(auto.trigger.to_dict()),
                    json.dumps([s.to_dict() for s in auto.steps]),
                    json.dumps(auto.output_destination.to_dict()) if auto.output_destination else None,
                    auto.created_at,
                    auto.updated_at,
                    auto.last_run_at,
                    auto.last_run_status,
                    auto.next_run_at,
                    1 if auto.is_draft else 0,
                    1 if auto.requires_approval else 0,
                    auto.human_schedule,
                    json.dumps(auto.metadata or {}),
                ),
            )
        return auto

    def delete_automation(self, automation_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM automations WHERE id = ?;", (automation_id,))
            return cursor.rowcount > 0

    def toggle_automation(self, automation_id: str, enabled: bool) -> AutomationDefinition | None:
        auto = self.get_automation(automation_id)
        if not auto:
            return None
        auto.enabled = enabled
        if enabled:
            auto.is_draft = False
        return self.save_automation(auto)

    def record_run_started(self, run: AutomationRunRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO automation_runs (
                    run_id, automation_id, automation_name, trigger_type, status,
                    started_at, completed_at, duration_seconds, input_payload_json,
                    output_result, error, step_runs_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    run.run_id,
                    run.automation_id,
                    run.automation_name,
                    run.trigger_type,
                    run.status.value if isinstance(run.status, RunStatus) else run.status,
                    run.started_at,
                    run.completed_at,
                    run.duration_seconds,
                    json.dumps(run.input_payload),
                    run.output_result,
                    run.error,
                    json.dumps(run.step_runs),
                ),
            )

    def record_run_completed(
        self,
        run_id: str,
        status: RunStatus,
        output_result: str | None,
        error: str | None,
        step_runs: list[dict[str, Any]],
        completed_at: str | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        comp_time = completed_at or datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE automation_runs
                SET status = ?, output_result = ?, error = ?, step_runs_json = ?,
                    completed_at = ?, duration_seconds = ?
                WHERE run_id = ?;
                """,
                (
                    status.value if isinstance(status, RunStatus) else status,
                    output_result,
                    error,
                    json.dumps(step_runs),
                    comp_time,
                    duration_seconds,
                    run_id,
                ),
            )

    def list_runs(self, automation_id: str | None = None, limit: int = 50) -> list[AutomationRunRecord]:
        query = (
            "SELECT run_id, automation_id, automation_name, trigger_type, status, "
            "started_at, completed_at, duration_seconds, input_payload_json, output_result, error, step_runs_json "
            "FROM automation_runs "
        )
        params: list[Any] = []
        if automation_id:
            query += "WHERE automation_id = ? "
            params.append(automation_id)
        query += "ORDER BY started_at DESC LIMIT ?;"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.execute(query, tuple(params))
            rows = cursor.fetchall()

        runs: list[AutomationRunRecord] = []
        for r in rows:
            in_payload = json.loads(r[8]) if r[8] else {}
            step_runs = json.loads(r[11]) if r[11] else []
            runs.append(
                AutomationRunRecord(
                    run_id=r[0],
                    automation_id=r[1],
                    automation_name=r[2],
                    trigger_type=r[3],
                    status=RunStatus(r[4]) if r[4] in [s.value for s in RunStatus] else RunStatus.PENDING,
                    started_at=r[5],
                    completed_at=r[6],
                    duration_seconds=r[7],
                    input_payload=in_payload,
                    output_result=r[9],
                    error=r[10],
                    step_runs=step_runs,
                )
            )
        return runs

    def get_run(self, run_id: str) -> AutomationRunRecord | None:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT run_id, automation_id, automation_name, trigger_type, status, "
                "started_at, completed_at, duration_seconds, input_payload_json, output_result, error, step_runs_json "
                "FROM automation_runs WHERE run_id = ?;",
                (run_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return AutomationRunRecord(
            run_id=row[0],
            automation_id=row[1],
            automation_name=row[2],
            trigger_type=row[3],
            status=RunStatus(row[4]) if row[4] in [s.value for s in RunStatus] else RunStatus.PENDING,
            started_at=row[5],
            completed_at=row[6],
            duration_seconds=row[7],
            input_payload=json.loads(row[8]) if row[8] else {},
            output_result=row[9],
            error=row[10],
            step_runs=json.loads(row[11]) if row[11] else [],
        )

    # ---------------------------------------------------------------------------
    # Automation Suggestions
    # ---------------------------------------------------------------------------

    def list_suggestions(self, status: str | None = "pending") -> list[AutomationSuggestion]:
        query = (
            "SELECT id, title, description, rationale, evidence_count, evidence_summary, "
            "trigger_json, steps_json, output_destination_json, status, created_at, automation_id "
            "FROM automation_suggestions "
        )
        params: list[Any] = []
        if status:
            query += "WHERE status = ? "
            params.append(status)
        query += "ORDER BY created_at DESC;"

        with self._get_connection() as conn:
            cursor = conn.execute(query, tuple(params))
            rows = cursor.fetchall()

        suggestions: list[AutomationSuggestion] = []
        for r in rows:
            trig_data = json.loads(r[6]) if r[6] else {}
            steps_data = json.loads(r[7]) if r[7] else []
            out_data = json.loads(r[8]) if r[8] else None

            suggestions.append(
                AutomationSuggestion(
                    id=r[0],
                    title=r[1],
                    description=r[2],
                    rationale=r[3],
                    evidence_count=r[4],
                    evidence_summary=r[5],
                    suggested_trigger=TriggerConfig.from_dict(trig_data),
                    suggested_steps=[PipelineStep.from_dict(s) for s in steps_data],
                    suggested_output=OutputDestination.from_dict(out_data) if out_data else None,
                    status=SuggestionStatus(r[9]) if r[9] in [s.value for s in SuggestionStatus] else SuggestionStatus.PENDING,
                    created_at=r[10],
                    automation_id=r[11],
                )
            )
        return suggestions

    def get_suggestion(self, suggestion_id: str) -> AutomationSuggestion | None:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, title, description, rationale, evidence_count, evidence_summary, "
                "trigger_json, steps_json, output_destination_json, status, created_at, automation_id "
                "FROM automation_suggestions WHERE id = ?;",
                (suggestion_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        trig_data = json.loads(row[6]) if row[6] else {}
        steps_data = json.loads(row[7]) if row[7] else []
        out_data = json.loads(row[8]) if row[8] else None

        return AutomationSuggestion(
            id=row[0],
            title=row[1],
            description=row[2],
            rationale=row[3],
            evidence_count=row[4],
            evidence_summary=row[5],
            suggested_trigger=TriggerConfig.from_dict(trig_data),
            suggested_steps=[PipelineStep.from_dict(s) for s in steps_data],
            suggested_output=OutputDestination.from_dict(out_data) if out_data else None,
            status=SuggestionStatus(row[9]) if row[9] in [s.value for s in SuggestionStatus] else SuggestionStatus.PENDING,
            created_at=row[10],
            automation_id=row[11],
        )

    def save_suggestion(self, suggestion: AutomationSuggestion) -> AutomationSuggestion:
        now = datetime.now(timezone.utc).isoformat()
        if not suggestion.created_at:
            suggestion.created_at = now

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO automation_suggestions (
                    id, title, description, rationale, evidence_count, evidence_summary,
                    trigger_json, steps_json, output_destination_json, status, created_at, automation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    rationale = excluded.rationale,
                    evidence_count = excluded.evidence_count,
                    evidence_summary = excluded.evidence_summary,
                    trigger_json = excluded.trigger_json,
                    steps_json = excluded.steps_json,
                    output_destination_json = excluded.output_destination_json,
                    status = excluded.status,
                    automation_id = excluded.automation_id;
                """,
                (
                    suggestion.id,
                    suggestion.title,
                    suggestion.description,
                    suggestion.rationale,
                    suggestion.evidence_count,
                    suggestion.evidence_summary,
                    json.dumps(suggestion.suggested_trigger.to_dict()),
                    json.dumps([s.to_dict() for s in suggestion.suggested_steps]),
                    json.dumps(suggestion.suggested_output.to_dict()) if suggestion.suggested_output else None,
                    suggestion.status.value if isinstance(suggestion.status, SuggestionStatus) else suggestion.status,
                    suggestion.created_at,
                    suggestion.automation_id,
                ),
            )
        return suggestion

    def dismiss_suggestion(self, suggestion_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE automation_suggestions SET status = ? WHERE id = ?;",
                (SuggestionStatus.DISMISSED.value, suggestion_id),
            )
            return cursor.rowcount > 0

    def accept_suggestion(self, suggestion_id: str) -> AutomationDefinition | None:
        suggestion = self.get_suggestion(suggestion_id)
        if not suggestion:
            return None

        # Create active automation from suggestion
        auto = AutomationDefinition(
            name=suggestion.title,
            description=suggestion.description,
            enabled=True,
            trigger=suggestion.suggested_trigger,
            steps=suggestion.suggested_steps,
            output_destination=suggestion.suggested_output,
            is_draft=False,
            requires_approval=False,
        )
        saved_auto = self.save_automation(auto)

        # Update suggestion status
        suggestion.status = SuggestionStatus.ACCEPTED
        suggestion.automation_id = saved_auto.id
        self.save_suggestion(suggestion)

        return saved_auto
