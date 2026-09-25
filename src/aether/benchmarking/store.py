"""SQLite persistence store for Benchmark Runs, Evolution Proposals, and Regression Alerts."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from aether.benchmarking.models import (
    AlertSeverity,
    BenchmarkMetrics,
    BenchmarkRun,
    BenchmarkTargetType,
    EvolutionProposal,
    ProposalStatus,
    RegressionAlert,
)


class BenchmarkingStore:
    """Persistent storage for workforce evaluations, automated evolutions, and regression guardrails."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS benchmark_runs (
                    id TEXT PRIMARY KEY,
                    suite_name TEXT,
                    target_type TEXT,
                    target_id TEXT,
                    target_name TEXT,
                    metrics TEXT,
                    overall_score REAL,
                    status TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    metadata TEXT
                );

                CREATE TABLE IF NOT EXISTS evolution_proposals (
                    id TEXT PRIMARY KEY,
                    target_agent TEXT,
                    benchmark_run_id TEXT,
                    title TEXT,
                    rationale TEXT,
                    suggested_prompt_addition TEXT,
                    suggested_preferred_model TEXT,
                    expected_quality_delta REAL,
                    status TEXT,
                    applied_at TEXT,
                    created_at TEXT,
                    metadata TEXT
                );

                CREATE TABLE IF NOT EXISTS regression_alerts (
                    id TEXT PRIMARY KEY,
                    benchmark_run_id TEXT,
                    target_id TEXT,
                    metric_name TEXT,
                    baseline_value REAL,
                    current_value REAL,
                    delta_percentage REAL,
                    severity TEXT,
                    message TEXT,
                    resolved INTEGER,
                    created_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_bm_target ON benchmark_runs(target_id);
                CREATE INDEX IF NOT EXISTS idx_bm_type ON benchmark_runs(target_type);
                CREATE INDEX IF NOT EXISTS idx_evo_agent ON evolution_proposals(target_agent);
                CREATE INDEX IF NOT EXISTS idx_evo_status ON evolution_proposals(status);
                CREATE INDEX IF NOT EXISTS idx_alerts_target ON regression_alerts(target_id);
                CREATE INDEX IF NOT EXISTS idx_alerts_resolved ON regression_alerts(resolved);
            """)

    # -------------------------------------------------------------------------
    # Benchmark Runs CRUD
    # -------------------------------------------------------------------------

    def save_run(self, run: BenchmarkRun) -> BenchmarkRun:
        """Create or update a benchmark execution run."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO benchmark_runs (
                    id, suite_name, target_type, target_id, target_name,
                    metrics, overall_score, status, started_at, completed_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.suite_name,
                    run.target_type.value if isinstance(run.target_type, BenchmarkTargetType) else run.target_type,
                    run.target_id,
                    run.target_name,
                    json.dumps(run.metrics.to_dict()),
                    run.overall_score,
                    run.status,
                    run.started_at,
                    run.completed_at,
                    json.dumps(run.metadata),
                ),
            )
        return run

    def get_run(self, run_id: str) -> Optional[BenchmarkRun]:
        """Fetch benchmark run by ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM benchmark_runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                return None
            return self._row_to_run(row)

    def list_runs(
        self,
        target_id: Optional[str] = None,
        target_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[BenchmarkRun]:
        """List benchmark runs with optional filtering."""
        query = "SELECT * FROM benchmark_runs WHERE 1=1"
        params: List[Any] = []
        if target_id:
            query += " AND target_id = ?"
            params.append(target_id)
        if target_type:
            query += " AND target_type = ?"
            params.append(target_type)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_run(r) for r in rows]

    def _row_to_run(self, row: sqlite3.Row) -> BenchmarkRun:
        return BenchmarkRun(
            id=row["id"],
            suite_name=row["suite_name"] or "default",
            target_type=BenchmarkTargetType(row["target_type"] or "agent"),
            target_id=row["target_id"] or "",
            target_name=row["target_name"] or "",
            metrics=BenchmarkMetrics.from_dict(json.loads(row["metrics"] or "{}")),
            overall_score=row["overall_score"] or 0.0,
            status=row["status"] or "completed",
            started_at=row["started_at"] or "",
            completed_at=row["completed_at"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    # -------------------------------------------------------------------------
    # Evolution Proposals CRUD
    # -------------------------------------------------------------------------

    def save_proposal(self, proposal: EvolutionProposal) -> EvolutionProposal:
        """Create or update an agent evolution proposal."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO evolution_proposals (
                    id, target_agent, benchmark_run_id, title, rationale,
                    suggested_prompt_addition, suggested_preferred_model,
                    expected_quality_delta, status, applied_at, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.id,
                    proposal.target_agent,
                    proposal.benchmark_run_id,
                    proposal.title,
                    proposal.rationale,
                    proposal.suggested_prompt_addition,
                    proposal.suggested_preferred_model,
                    proposal.expected_quality_delta,
                    proposal.status.value if isinstance(proposal.status, ProposalStatus) else proposal.status,
                    proposal.applied_at,
                    proposal.created_at,
                    json.dumps(proposal.metadata),
                ),
            )
        return proposal

    def get_proposal(self, proposal_id: str) -> Optional[EvolutionProposal]:
        """Fetch proposal by ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM evolution_proposals WHERE id = ?", (proposal_id,)).fetchone()
            if not row:
                return None
            return self._row_to_proposal(row)

    def list_proposals(
        self, target_agent: Optional[str] = None, status: Optional[str] = None
    ) -> List[EvolutionProposal]:
        """List evolution proposals."""
        query = "SELECT * FROM evolution_proposals WHERE 1=1"
        params: List[Any] = []
        if target_agent:
            query += " AND target_agent = ?"
            params.append(target_agent)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_proposal(r) for r in rows]

    def update_proposal_status(
        self, proposal_id: str, status: ProposalStatus
    ) -> Optional[EvolutionProposal]:
        """Update status of a proposal."""
        prop = self.get_proposal(proposal_id)
        if not prop:
            return None
        prop.status = status
        if status == ProposalStatus.APPLIED:
            prop.applied_at = datetime.now(timezone.utc).isoformat()
        return self.save_proposal(prop)

    def _row_to_proposal(self, row: sqlite3.Row) -> EvolutionProposal:
        return EvolutionProposal(
            id=row["id"],
            target_agent=row["target_agent"] or "",
            benchmark_run_id=row["benchmark_run_id"] or "",
            title=row["title"] or "",
            rationale=row["rationale"] or "",
            suggested_prompt_addition=row["suggested_prompt_addition"] or "",
            suggested_preferred_model=row["suggested_preferred_model"],
            expected_quality_delta=row["expected_quality_delta"] or 0.0,
            status=ProposalStatus(row["status"] or "pending"),
            applied_at=row["applied_at"],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    # -------------------------------------------------------------------------
    # Regression Alerts CRUD
    # -------------------------------------------------------------------------

    def save_alert(self, alert: RegressionAlert) -> RegressionAlert:
        """Create or update a regression alert."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO regression_alerts (
                    id, benchmark_run_id, target_id, metric_name,
                    baseline_value, current_value, delta_percentage,
                    severity, message, resolved, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.id,
                    alert.benchmark_run_id,
                    alert.target_id,
                    alert.metric_name,
                    alert.baseline_value,
                    alert.current_value,
                    alert.delta_percentage,
                    alert.severity.value if isinstance(alert.severity, AlertSeverity) else alert.severity,
                    alert.message,
                    1 if alert.resolved else 0,
                    alert.created_at,
                ),
            )
        return alert

    def list_alerts(
        self, target_id: Optional[str] = None, unresolved_only: bool = False
    ) -> List[RegressionAlert]:
        """List regression alerts."""
        query = "SELECT * FROM regression_alerts WHERE 1=1"
        params: List[Any] = []
        if target_id:
            query += " AND target_id = ?"
            params.append(target_id)
        if unresolved_only:
            query += " AND resolved = 0"
        query += " ORDER BY created_at DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_alert(r) for r in rows]

    def get_alert(self, alert_id: str) -> Optional[RegressionAlert]:
        """Fetch alert by ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM regression_alerts WHERE id = ?", (alert_id,)).fetchone()
            if not row:
                return None
            return self._row_to_alert(row)

    def resolve_alert(self, alert_id: str) -> Optional[RegressionAlert]:
        """Mark an alert as resolved."""
        alert = self.get_alert(alert_id)
        if not alert:
            return None
        alert.resolved = True
        return self.save_alert(alert)

    def _row_to_alert(self, row: sqlite3.Row) -> RegressionAlert:
        return RegressionAlert(
            id=row["id"],
            benchmark_run_id=row["benchmark_run_id"] or "",
            target_id=row["target_id"] or "",
            metric_name=row["metric_name"] or "",
            baseline_value=row["baseline_value"] or 0.0,
            current_value=row["current_value"] or 0.0,
            delta_percentage=row["delta_percentage"] or 0.0,
            severity=AlertSeverity(row["severity"] or "medium"),
            message=row["message"] or "",
            resolved=bool(row["resolved"]),
            created_at=row["created_at"],
        )

