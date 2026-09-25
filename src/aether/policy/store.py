"""
SQLite storage for Workspace Policies and Autopilot Governance.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

from aether.policy.models import AutopilotTier, WorkspacePolicy


class PolicyStore:
    """Persistent SQLite store for WorkspacePolicy governance records."""

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
                CREATE TABLE IF NOT EXISTS workspace_policies (
                    workspace_id TEXT PRIMARY KEY,
                    autopilot_tier TEXT NOT NULL,
                    max_budget_per_mission REAL NOT NULL,
                    monthly_spending_cap REAL NOT NULL,
                    current_monthly_spend REAL NOT NULL,
                    prohibited_actions TEXT NOT NULL,
                    require_quality_gate INTEGER NOT NULL,
                    allowed_connectors TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def get_policy(self, workspace_id: str) -> WorkspacePolicy:
        """Retrieves active policy for a workspace or initializes default."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM workspace_policies WHERE workspace_id = ?", (workspace_id,))
            row = cur.fetchone()
            if not row:
                default_policy = WorkspacePolicy(workspace_id=workspace_id)
                self.save_policy(default_policy)
                return default_policy

            return WorkspacePolicy(
                workspace_id=row["workspace_id"],
                autopilot_tier=AutopilotTier(row["autopilot_tier"]),
                max_budget_per_mission=float(row["max_budget_per_mission"]),
                monthly_spending_cap=float(row["monthly_spending_cap"]),
                current_monthly_spend=float(row["current_monthly_spend"]),
                prohibited_actions=json.loads(row["prohibited_actions"]),
                require_quality_gate=bool(row["require_quality_gate"]),
                allowed_connectors=json.loads(row["allowed_connectors"]),
                updated_at=row["updated_at"],
            )

    def save_policy(self, policy: WorkspacePolicy) -> WorkspacePolicy:
        """Persists or updates a workspace policy."""
        tier_val = policy.autopilot_tier.value if hasattr(policy.autopilot_tier, "value") else str(policy.autopilot_tier)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workspace_policies (
                    workspace_id,
                    autopilot_tier,
                    max_budget_per_mission,
                    monthly_spending_cap,
                    current_monthly_spend,
                    prohibited_actions,
                    require_quality_gate,
                    allowed_connectors,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id) DO UPDATE SET
                    autopilot_tier = excluded.autopilot_tier,
                    max_budget_per_mission = excluded.max_budget_per_mission,
                    monthly_spending_cap = excluded.monthly_spending_cap,
                    current_monthly_spend = excluded.current_monthly_spend,
                    prohibited_actions = excluded.prohibited_actions,
                    require_quality_gate = excluded.require_quality_gate,
                    allowed_connectors = excluded.allowed_connectors,
                    updated_at = excluded.updated_at
                """,
                (
                    policy.workspace_id,
                    tier_val,
                    policy.max_budget_per_mission,
                    policy.monthly_spending_cap,
                    policy.current_monthly_spend,
                    json.dumps(policy.prohibited_actions),
                    1 if policy.require_quality_gate else 0,
                    json.dumps(policy.allowed_connectors),
                    policy.updated_at,
                ),
            )
            conn.commit()
        return policy

    def record_spend(self, workspace_id: str, amount: float) -> WorkspacePolicy:
        """Increments current monthly spend for the workspace."""
        policy = self.get_policy(workspace_id)
        policy.current_monthly_spend += amount
        return self.save_policy(policy)
