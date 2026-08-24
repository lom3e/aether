"""
AutomationStore — SQLite persistence for Automation Workflows and Execution Run Logs.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aether.automation.models import (
    AutomationDefinition,
    AutomationRunRecord,
    OutputDestination,
    PipelineStep,
    RunStatus,
    TriggerConfig,
)
from aether.core.sqlite import get_sqlite_connection


class AutomationStore:
    """Manages persistent automation workflows and run execution history."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        if self.db_path == ":memory:":
            self.db_path = f"file:memdb_auto_{uuid.uuid4().hex}?mode=memory&cache=shared"
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return get_sqlite_connection(self.db_path)

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
                    next_run_at TEXT
                );
                """
            )
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

    def list_automations(self) -> list[AutomationDefinition]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, name, description, enabled, team_name, trigger_json, steps_json, "
                "output_destination_json, created_at, updated_at, last_run_at, last_run_status, next_run_at "
                "FROM automations ORDER BY created_at ASC;"
            )
            rows = cursor.fetchall()

        res: list[AutomationDefinition] = []
        for r in rows:
            trigger_data = json.loads(r[5]) if r[5] else {}
            steps_data = json.loads(r[6]) if r[6] else []
            out_data = json.loads(r[7]) if r[7] else None

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
                )
            )
        return res

    def get_automation(self, automation_id: str) -> AutomationDefinition | None:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, name, description, enabled, team_name, trigger_json, steps_json, "
                "output_destination_json, created_at, updated_at, last_run_at, last_run_status, next_run_at "
                "FROM automations WHERE id = ?;",
                (automation_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        trigger_data = json.loads(row[5]) if row[5] else {}
        steps_data = json.loads(row[6]) if row[6] else []
        out_data = json.loads(row[7]) if row[7] else None

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
                    output_destination_json, created_at, updated_at, last_run_at, last_run_status, next_run_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    next_run_at = excluded.next_run_at;
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
