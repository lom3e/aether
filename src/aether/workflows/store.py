"""
SQLite storage for Visual Workflows.
Persists workflow graphs, node positions, and compilation links.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

from aether.workflows.models import Workflow


class WorkflowStore:
    """Persistent SQLite store for visual workflow definitions."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    graph_json TEXT NOT NULL,
                    compiled_mission_id TEXT,
                    compiled_automation_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflows_workspace ON workflows(workspace_id)"
            )
            conn.commit()

    def list_workflows(self, workspace_id: str) -> list[Workflow]:
        """Lists all visual workflows for a workspace."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM workflows WHERE workspace_id = ? ORDER BY updated_at DESC",
                (workspace_id,),
            )
            rows = cur.fetchall()
            workflows: list[Workflow] = []
            for r in rows:
                workflows.append(
                    Workflow.from_dict({
                        "id": r["id"],
                        "workspace_id": r["workspace_id"],
                        "name": r["name"],
                        "description": r["description"] or "",
                        "graph": json.loads(r["graph_json"]),
                        "compiled_mission_id": r["compiled_mission_id"],
                        "compiled_automation_id": r["compiled_automation_id"],
                        "created_at": r["created_at"],
                        "updated_at": r["updated_at"],
                    })
                )
            return workflows

    def get_workflow(self, workflow_id: str, workspace_id: str | None = None) -> Workflow | None:
        """Retrieves a specific visual workflow by ID."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            if workspace_id:
                cur.execute(
                    "SELECT * FROM workflows WHERE id = ? AND workspace_id = ?",
                    (workflow_id, workspace_id),
                )
            else:
                cur.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
            r = cur.fetchone()
            if not r:
                return None

            return Workflow.from_dict({
                "id": r["id"],
                "workspace_id": r["workspace_id"],
                "name": r["name"],
                "description": r["description"] or "",
                "graph": json.loads(r["graph_json"]),
                "compiled_mission_id": r["compiled_mission_id"],
                "compiled_automation_id": r["compiled_automation_id"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            })

    def save_workflow(self, workflow: Workflow) -> Workflow:
        """Persists or updates a visual workflow."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workflows (
                    id,
                    workspace_id,
                    name,
                    description,
                    graph_json,
                    compiled_mission_id,
                    compiled_automation_id,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    graph_json = excluded.graph_json,
                    compiled_mission_id = excluded.compiled_mission_id,
                    compiled_automation_id = excluded.compiled_automation_id,
                    updated_at = excluded.updated_at
                """,
                (
                    workflow.id,
                    workflow.workspace_id,
                    workflow.name,
                    workflow.description,
                    json.dumps(workflow.graph.to_dict()),
                    workflow.compiled_mission_id,
                    workflow.compiled_automation_id,
                    workflow.created_at,
                    workflow.updated_at,
                ),
            )
            conn.commit()
        return workflow

    def delete_workflow(self, workflow_id: str, workspace_id: str) -> bool:
        """Deletes a visual workflow."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM workflows WHERE id = ? AND workspace_id = ?",
                (workflow_id, workspace_id),
            )
            conn.commit()
            return cur.rowcount > 0
