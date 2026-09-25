"""
Persistent SQLite storage for Autonomous Goals and multi-stage execution traces.
Supports ACID persistence, WAL mode, transaction isolation, and querying.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

from aether.autonomy.models import AutonomousGoal, AutonomousGoalStatus, AutonomousStage


class AutonomousGoalStore:
    """Production SQLite store for autonomous operational loop goals."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS autonomous_goals (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    raw_prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stages_json TEXT NOT NULL,
                    active_stage_index INTEGER NOT NULL DEFAULT 0,
                    allocated_node_id TEXT,
                    allocated_tier TEXT,
                    deliverables_json TEXT NOT NULL,
                    approval_execution_id TEXT,
                    learning_summary TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_autonomy_workspace ON autonomous_goals(workspace_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_autonomy_status ON autonomous_goals(status)")

    def save_goal(self, goal: AutonomousGoal) -> AutonomousGoal:
        stages_data = [s.to_dict() for s in goal.stages]
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO autonomous_goals (
                    id, workspace_id, goal, raw_prompt, status, stages_json,
                    active_stage_index, allocated_node_id, allocated_tier,
                    deliverables_json, approval_execution_id, learning_summary,
                    error, created_at, updated_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    stages_json=excluded.stages_json,
                    active_stage_index=excluded.active_stage_index,
                    allocated_node_id=excluded.allocated_node_id,
                    allocated_tier=excluded.allocated_tier,
                    deliverables_json=excluded.deliverables_json,
                    approval_execution_id=excluded.approval_execution_id,
                    learning_summary=excluded.learning_summary,
                    error=excluded.error,
                    updated_at=excluded.updated_at,
                    completed_at=excluded.completed_at
                """,
                (
                    goal.id,
                    goal.workspace_id,
                    goal.goal,
                    goal.raw_prompt,
                    goal.status.value if isinstance(goal.status, AutonomousGoalStatus) else str(goal.status),
                    json.dumps(stages_data),
                    goal.active_stage_index,
                    goal.allocated_node_id,
                    goal.allocated_tier,
                    json.dumps(goal.deliverables),
                    goal.approval_execution_id,
                    goal.learning_summary,
                    goal.error,
                    goal.created_at,
                    goal.updated_at,
                    goal.completed_at,
                ),
            )
        return goal

    def get_goal(self, goal_id: str) -> AutonomousGoal | None:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM autonomous_goals WHERE id = ?", (goal_id,)).fetchone()
            if not row:
                return None
            return self._row_to_goal(row)

    def list_goals(self, workspace_id: str, limit: int = 50) -> list[AutonomousGoal]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM autonomous_goals WHERE workspace_id = ? ORDER BY created_at DESC LIMIT ?",
                (workspace_id, limit),
            ).fetchall()
            return [self._row_to_goal(r) for r in rows]

    def delete_goal(self, goal_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM autonomous_goals WHERE id = ?", (goal_id,))
            return cursor.rowcount > 0

    def _row_to_goal(self, row: sqlite3.Row) -> AutonomousGoal:
        try:
            stages_list = json.loads(row["stages_json"])
            stages = [AutonomousStage.from_dict(s) for s in stages_list]
        except Exception:
            stages = []

        try:
            delivs = json.loads(row["deliverables_json"])
        except Exception:
            delivs = []

        return AutonomousGoal(
            id=row["id"],
            workspace_id=row["workspace_id"],
            goal=row["goal"],
            raw_prompt=row["raw_prompt"],
            status=AutonomousGoalStatus.from_str(row["status"]),
            stages=stages,
            active_stage_index=row["active_stage_index"],
            allocated_node_id=row["allocated_node_id"],
            allocated_tier=row["allocated_tier"],
            deliverables=delivs,
            approval_execution_id=row["approval_execution_id"],
            learning_summary=row["learning_summary"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )
