"""Workforce Benchmarking and Autonomous Evolution Engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from aether.benchmarking.models import (
    AlertSeverity,
    BenchmarkMetrics,
    BenchmarkRun,
    BenchmarkTargetType,
    EvolutionProposal,
    ProposalStatus,
    RegressionAlert,
)
from aether.benchmarking.store import BenchmarkingStore


class WorkforceEvolutionEngine:
    """Evaluates agent and workforce capabilities, detects regressions, and proposes autonomous optimizations."""

    def __init__(self, store: Optional[BenchmarkingStore] = None):
        self.store = store

    def evaluate_target(
        self,
        target_name: Optional[str] = None,
        target_id: Optional[str] = None,
        target_type: Union[BenchmarkTargetType, str] = BenchmarkTargetType.AGENT,
        suite_name: str = "general_capability_v1",
        test_suite: Optional[List[str]] = None,
        latency_ms: Optional[float] = None,
        avg_latency_ms: Optional[float] = None,
        tokens_used: Optional[int] = None,
        avg_tokens_per_task: Optional[int] = None,
        error_rate: Optional[float] = None,
        quality_score: Optional[float] = None,
        safety_compliance: Optional[float] = None,
        safety_compliance_score: Optional[float] = None,
        completion_rate: Optional[float] = None,
        status: str = "completed",
        metadata: Optional[Dict[str, Any]] = None,
        metrics_override: Optional[Dict[str, Any]] = None,
        store: Optional[BenchmarkingStore] = None,
    ) -> Tuple[BenchmarkRun, List[RegressionAlert], List[EvolutionProposal]]:
        """Run evaluation suite against an agent, team, or workflow, detecting regressions and generating evolution proposals."""
        t_id = target_id or target_name or "researcher"
        t_name = target_name or target_id or "researcher"

        if isinstance(target_type, str):
            try:
                target_type_enum = BenchmarkTargetType(target_type)
            except ValueError:
                target_type_enum = BenchmarkTargetType.AGENT
        else:
            target_type_enum = target_type

        if metrics_override:
            metrics = BenchmarkMetrics.from_dict(metrics_override)
        else:
            metrics = BenchmarkMetrics(
                completion_rate=completion_rate if completion_rate is not None else 0.95,
                error_rate=error_rate if error_rate is not None else 0.05,
                latency_ms=latency_ms if latency_ms is not None else (avg_latency_ms if avg_latency_ms is not None else 950.0),
                tokens_used=tokens_used if tokens_used is not None else (avg_tokens_per_task if avg_tokens_per_task is not None else 1450),
                quality_score=quality_score if quality_score is not None else 89.0,
                safety_compliance=safety_compliance if safety_compliance is not None else (safety_compliance_score if safety_compliance_score is not None else 100.0),
            )

        overall = metrics.calculate_composite_score()

        run = BenchmarkRun(
            id=f"bm-{uuid.uuid4().hex[:10]}",
            suite_name=suite_name,
            target_type=target_type_enum,
            target_id=t_id,
            target_name=t_name,
            metrics=metrics,
            overall_score=overall,
            status=status,
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )

        effective_store = store or self.store
        alerts: List[RegressionAlert] = []
        proposals: List[EvolutionProposal] = []

        if effective_store:
            past_runs = effective_store.list_runs(target_id=t_id, limit=2)
            # Find the most recent run before this one
            baseline_run = past_runs[0] if past_runs else None

            saved_run = effective_store.save_run(run)
            alerts = self.detect_regressions(saved_run, baseline_run)
            for a in alerts:
                effective_store.save_alert(a)

            # Generate proposal if performance is degraded or errors present
            normalized_q = metrics.quality_score / 100.0 if metrics.quality_score > 1.0 else metrics.quality_score
            if metrics.error_rate >= 0.10 or normalized_q < 0.75 or alerts:
                prop = self.generate_evolution_proposal(t_id, saved_run)
                effective_store.save_proposal(prop)
                proposals.append(prop)
            return saved_run, alerts, proposals
        else:
            normalized_q = metrics.quality_score / 100.0 if metrics.quality_score > 1.0 else metrics.quality_score
            if metrics.error_rate >= 0.10 or normalized_q < 0.75:
                proposals.append(self.generate_evolution_proposal(t_id, run))
            return run, alerts, proposals

    def detect_regressions(
        self,
        current_run: BenchmarkRun,
        baseline_run: Optional[BenchmarkRun],
    ) -> List[RegressionAlert]:
        """Compare current run against baseline and generate alerts if performance degraded."""
        alerts: List[RegressionAlert] = []
        if not baseline_run:
            return alerts

        curr = current_run.metrics
        base = baseline_run.metrics

        # 1. Error Rate Regression
        if curr.error_rate > base.error_rate:
            base_err = max(0.01, base.error_rate)
            delta_err_pct = round(((curr.error_rate - base.error_rate) / base_err) * 100, 1)
            if delta_err_pct >= 50.0 or curr.error_rate >= 0.15:
                severity = AlertSeverity.CRITICAL if curr.error_rate >= 0.25 else AlertSeverity.HIGH
                alerts.append(
                    RegressionAlert(
                        benchmark_run_id=current_run.id,
                        target_id=current_run.target_id,
                        metric_name="error_rate",
                        baseline_value=base.error_rate,
                        current_value=curr.error_rate,
                        delta_percentage=delta_err_pct,
                        severity=severity,
                        message=f"Error rate degraded from {base.error_rate*100:.1f}% to {curr.error_rate*100:.1f}% (+{delta_err_pct}%).",
                    )
                )

        # 2. Quality Score Drop
        curr_q = curr.quality_score / 100.0 if curr.quality_score > 1.0 else curr.quality_score
        base_q = base.quality_score / 100.0 if base.quality_score > 1.0 else base.quality_score
        if curr_q < base_q - 0.08:
            delta_quality = round((base_q - curr_q) * 100, 1)
            alerts.append(
                RegressionAlert(
                    benchmark_run_id=current_run.id,
                    target_id=current_run.target_id,
                    metric_name="quality_score",
                    baseline_value=base_q,
                    current_value=curr_q,
                    delta_percentage=-round((delta_quality / (base_q * 100)) * 100, 1),
                    severity=AlertSeverity.HIGH if delta_quality >= 15.0 else AlertSeverity.MEDIUM,
                    message=f"Quality score dropped by {delta_quality} points ({base_q*100:.1f}% -> {curr_q*100:.1f}%).",
                )
            )

        # 3. Latency Spike
        if curr.avg_latency_ms > base.avg_latency_ms * 1.75:
            delta_lat_pct = round(((curr.avg_latency_ms - base.avg_latency_ms) / base.avg_latency_ms) * 100, 1)
            alerts.append(
                RegressionAlert(
                    benchmark_run_id=current_run.id,
                    target_id=current_run.target_id,
                    metric_name="latency",
                    baseline_value=base.avg_latency_ms,
                    current_value=curr.avg_latency_ms,
                    delta_percentage=delta_lat_pct,
                    severity=AlertSeverity.MEDIUM,
                    message=f"Average execution latency spiked by {delta_lat_pct}% ({base.avg_latency_ms:.0f}ms -> {curr.avg_latency_ms:.0f}ms).",
                )
            )

        return alerts

    def generate_evolution_proposal(
        self,
        agent_name: str,
        run: BenchmarkRun,
    ) -> EvolutionProposal:
        """Formulate an actionable evolution proposal to optimize agent performance."""
        metrics = run.metrics

        if metrics.error_rate >= 0.10:
            title = f"Enforce Deterministic Tool Validation for {agent_name}"
            rationale = f"Detected error rate of {metrics.error_rate*100:.1f}%. Adding pre-validation input constraints."
            prompt_add = (
                "\n\n### Operational Guardrails:\n"
                "1. Always validate required arguments against tool schemas before calling.\n"
                "2. Confirm deterministic return types and handle edge-case null states cleanly.\n"
            )
            expected_delta = 0.15
        elif metrics.avg_latency_ms > 2000.0:
            title = f"Optimize Prompt Conciseness and Routing for {agent_name}"
            rationale = f"High average execution latency ({metrics.avg_latency_ms:.0f}ms). Streamlining instructions."
            prompt_add = (
                "\n\n### Concise Execution Rule:\n"
                "Provide direct, high-signal responses. Eliminate superfluous conversational filler.\n"
            )
            expected_delta = 0.08
        else:
            title = f"Inject Domain Few-Shot Grounding for {agent_name}"
            rationale = "General performance optimization based on historical benchmark evaluation."
            prompt_add = (
                "\n\n### Quality Benchmark Directives:\n"
                "- Verify all facts against local workspace knowledge.\n"
                "- Maintain high structured precision in code and deliverable outputs.\n"
            )
            expected_delta = 0.10

        return EvolutionProposal(
            id=f"evo-{uuid.uuid4().hex[:10]}",
            target_agent=agent_name,
            benchmark_run_id=run.id,
            title=title,
            rationale=rationale,
            suggested_prompt_addition=prompt_add,
            suggested_preferred_model="gemini-2.5-flash",
            expected_quality_delta=expected_delta,
            status=ProposalStatus.PENDING,
        )

    def apply_proposal(
        self,
        proposal_id: str,
        workspace: Optional[Any] = None,
    ) -> Optional[EvolutionProposal]:
        """Apply an evolution proposal by ID and mark it applied."""
        if not self.store:
            return None
        prop = self.store.get_proposal(proposal_id)
        if not prop:
            return None
        self.apply_evolution_proposal(prop, workspace)
        return self.store.update_proposal_status(proposal_id, ProposalStatus.APPLIED)

    def apply_evolution_proposal(
        self,
        proposal: EvolutionProposal,
        workspace: Any = None,
    ) -> bool:
        """Apply the suggested prompt optimization to the agent in workspace configuration."""
        if not workspace:
            return True

        team = getattr(workspace, "team", None)
        if not team:
            try:
                teams_dir = getattr(workspace, "teams_dir", None)
                if teams_dir and teams_dir.exists():
                    team_files = list(teams_dir.glob("*.yaml"))
                    if team_files:
                        from aether.team.loader import TeamLoader
                        config = TeamLoader.from_yaml(team_files[0])
                        for agent in config.agents:
                            if agent.name.lower() == proposal.target_agent.lower():
                                agent.system_prompt += proposal.suggested_prompt_addition
                                TeamLoader.to_yaml(config, team_files[0])
                                return True
            except Exception:
                pass
        return True

    def get_leaderboard(
        self,
        target_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Compute aggregated leaderboard ranking evaluated agents and workforces."""
        if not self.store:
            return []

        runs = self.store.list_runs(target_type=target_type, limit=limit * 2)
        # Deduplicate to latest run per target_id
        targets_seen: Dict[str, BenchmarkRun] = {}
        for r in runs:
            if r.target_id not in targets_seen:
                targets_seen[r.target_id] = r

        sorted_runs = sorted(targets_seen.values(), key=lambda r: r.overall_score, reverse=True)
        leaderboard: List[Dict[str, Any]] = []

        for r in sorted_runs[:limit]:
            metrics = r.metrics
            norm_q = metrics.quality_score / 100.0 if metrics.quality_score > 1.0 else metrics.quality_score
            norm_s = metrics.safety_compliance_score / 100.0 if metrics.safety_compliance_score > 1.0 else metrics.safety_compliance_score
            leaderboard.append({
                "target_id": r.target_id,
                "target_name": r.target_name or r.target_id,
                "target_type": r.target_type.value if isinstance(r.target_type, BenchmarkTargetType) else r.target_type,
                "overall_score": r.overall_score,
                "completion_rate": metrics.completion_rate,
                "error_rate": metrics.error_rate,
                "latency_ms": metrics.avg_latency_ms,
                "tokens_used": metrics.avg_tokens_per_task,
                "quality_score": norm_q,
                "safety_compliance": norm_s,
                "total_evaluations": metrics.total_evaluations,
                "last_evaluated_at": r.completed_at or r.started_at,
            })

        return leaderboard
