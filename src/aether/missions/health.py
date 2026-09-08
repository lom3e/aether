"""
Workforce Health & Operational Telemetry Engine.
Computes deterministic reliability metrics, execution durations, tool error rates,
per-agent health metrics, and data-backed diagnostic insights strictly from
real runtime execution records and persisted SQLite activities.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from aether.missions.store import MissionStore

logger = logging.getLogger(__name__)


@dataclass
class AgentHealthMetric:
    agent_id: str
    name: str
    role: str
    provider: str | None = None
    model: str | None = None
    status: str = "healthy"  # "healthy", "active", "degraded", "idle"
    tasks_assigned: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    tools_executed: int = 0
    tool_failures: int = 0
    reworks_count: int = 0
    success_rate: float = 100.0
    average_latency_ms: float | None = None
    last_active: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HealthInsight:
    id: str
    category: str  # "reliability", "performance", "quality", "governance"
    level: str     # "success", "info", "warning", "error"
    title: str
    detail: str
    data_points: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkforceHealthSummary:
    team_name: str
    scope: str  # "execution", "mission", "workspace"
    mission_id: str | None
    execution_id: str | None
    overall_status: str  # "healthy", "active", "degraded"
    total_executions: int
    completed_executions: int
    failed_executions: int
    execution_success_rate: float
    total_milestones: int
    completed_milestones: int
    milestone_success_rate: float
    total_tools_executed: int
    tool_failures: int
    tool_error_rate: float
    rework_count: int
    rework_rate: float
    approvals_count: int
    average_execution_duration_sec: float
    average_milestone_duration_sec: float
    agents: list[AgentHealthMetric]
    insights: list[HealthInsight]

    @property
    def rework_cycles_count(self) -> int:
        return self.rework_count

    @property
    def agent_metrics(self) -> list[AgentHealthMetric]:
        return self.agents

    @property
    def diagnostic_insights(self) -> list[HealthInsight]:
        return self.insights

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        res["agents"] = [a.to_dict() if hasattr(a, "to_dict") else a for a in self.agents]
        res["agent_metrics"] = res["agents"]
        res["insights"] = [i.to_dict() if hasattr(i, "to_dict") else i for i in self.insights]
        res["diagnostic_insights"] = res["insights"]
        res["rework_cycles_count"] = self.rework_count
        return res


class WorkforceHealthAnalyzer:
    """
    Aggregates factual metrics from SQLite mission_executions, mission_execution_milestones,
    and conversation_activities.
    """

    def __init__(self, store: MissionStore, team_resolver: Any = None) -> None:
        self.store = store
        self.team_resolver = team_resolver

    def analyze(
        self,
        mission_id: str | None = None,
        execution_id: str | None = None,
        team_name: str | None = None,
    ) -> WorkforceHealthSummary:
        """
        Calculates health metrics scoped to an execution, a mission, or the global workforce.
        """
        resolved_team = team_name or "Workforce"
        scope = "execution" if execution_id else ("mission" if mission_id else "workspace")

        executions = []
        if execution_id:
            exec_obj = self.store.get_execution(execution_id)
            if exec_obj:
                executions = [exec_obj]
                resolved_team = exec_obj.team_name or resolved_team
        elif mission_id:
            executions = self.store.list_executions(mission_id)
            mission = self.store.get_mission(mission_id, include_milestones=False)
            if mission and mission.team_name:
                resolved_team = mission.team_name
        else:
            # Workspace scope: fetch all executions across missions
            with self.store._get_connection() as conn:
                rows = conn.execute("SELECT id FROM mission_executions ORDER BY started_at DESC LIMIT 100").fetchall()
                for r in rows:
                    e = self.store.get_execution(r["id"])
                    if e:
                        executions.append(e)

        # 1. Execution Aggregates
        total_execs = len(executions)
        completed_execs = sum(1 for e in executions if e.status.value == "completed")
        failed_execs = sum(1 for e in executions if e.status.value in ("failed", "interrupted"))
        exec_success_rate = (completed_execs / total_execs * 100.0) if total_execs > 0 else 100.0

        durations = [e.duration_seconds for e in executions if e.duration_seconds and e.duration_seconds > 0]
        avg_exec_dur = (sum(durations) / len(durations)) if durations else 0.0

        # 2. Milestones Aggregates
        all_milestones = []
        for e in executions:
            ems = self.store.get_execution_milestones(e.id)
            all_milestones.extend(ems)

        total_milestones = len(all_milestones)
        completed_milestones = sum(1 for m in all_milestones if m.status.value == "completed")
        milestone_success_rate = (completed_milestones / total_milestones * 100.0) if total_milestones > 0 else 100.0
        total_reworks = sum(getattr(m, "rework_count", 0) for m in all_milestones)
        rework_rate = (total_reworks / total_milestones * 100.0) if total_milestones > 0 else 0.0

        # Milestone durations where available
        ms_durations = []
        for m in all_milestones:
            if m.started_at and m.completed_at:
                try:
                    t1 = datetime.fromisoformat(m.started_at.replace("Z", "+00:00"))
                    t2 = datetime.fromisoformat(m.completed_at.replace("Z", "+00:00"))
                    diff = (t2 - t1).total_seconds()
                    if diff >= 0:
                        ms_durations.append(diff)
                except Exception:
                    pass
        avg_ms_dur = (sum(ms_durations) / len(ms_durations)) if ms_durations else 0.0

        # 3. Conversation Activities Metrics
        target_exec_ids = {e.id for e in executions}
        acts = self._fetch_activities_for_executions(target_exec_ids, mission_id)

        tool_calls_count = 0
        tool_failures_count = 0
        approvals_count = 0
        total_activity_reworks = 0
        agent_stats: dict[str, dict[str, Any]] = {}

        for act in acts:
            act_type = act.get("activity_type", "")
            agent = act.get("agent") or "System"
            meta = act.get("metadata") or {}

            if agent not in agent_stats:
                agent_stats[agent] = {
                    "tasks_assigned": 0,
                    "tasks_completed": 0,
                    "tasks_failed": 0,
                    "tools_executed": 0,
                    "tool_failures": 0,
                    "reworks_count": 0,
                    "latencies": [],
                    "last_active": None,
                }

            st = agent_stats[agent]
            t_stamp = act.get("created_at")
            if t_stamp:
                if not st["last_active"] or t_stamp > st["last_active"]:
                    st["last_active"] = t_stamp

            # Tool metrics
            if "tool" in act_type:
                tool_calls_count += 1
                st["tools_executed"] += 1
                is_err = meta.get("is_error", False) or "error" in act_type.lower()
                if is_err:
                    tool_failures_count += 1
                    st["tool_failures"] += 1
                if meta.get("duration_ms"):
                    st["latencies"].append(float(meta["duration_ms"]))

            # Task & lifecycle metrics
            if "task_started" in act_type or "agent_dispatched" in act_type:
                st["tasks_assigned"] += 1
            elif "task_completed" in act_type:
                st["tasks_completed"] += 1
            elif "task_failed" in act_type:
                st["tasks_failed"] += 1

            if "rework" in act_type:
                st["reworks_count"] += 1
                total_activity_reworks += 1

            if "approval" in act_type:
                approvals_count += 1

        total_reworks = max(sum(getattr(m, "rework_count", 0) for m in all_milestones), total_activity_reworks)
        rework_rate = (total_reworks / total_milestones * 100.0) if total_milestones > 0 else 0.0
        tool_error_rate = (tool_failures_count / tool_calls_count * 100.0) if tool_calls_count > 0 else 0.0

        # 4. Resolve Workforce Agents List
        known_agents = self._resolve_known_agents(resolved_team)
        agent_metrics: list[AgentHealthMetric] = []

        all_agent_names = set(known_agents.keys()) | set(agent_stats.keys())
        for name in sorted(all_agent_names):
            if name.lower() in ("system", "coordinator_system"):
                continue
            cfg = known_agents.get(name, {})
            st = agent_stats.get(name, {
                "tasks_assigned": 0,
                "tasks_completed": 0,
                "tasks_failed": 0,
                "tools_executed": 0,
                "tool_failures": 0,
                "reworks_count": 0,
                "latencies": [],
                "last_active": None,
            })

            tot_tasks = st["tasks_assigned"]
            failed_tasks = st["tasks_failed"] + st["tool_failures"]
            completed_tasks = st["tasks_completed"] or (tot_tasks - failed_tasks if tot_tasks > failed_tasks else tot_tasks)
            denom = tot_tasks or (completed_tasks + failed_tasks)
            success_rate = ((denom - failed_tasks) / denom * 100.0) if denom > 0 else 100.0

            avg_lat = (sum(st["latencies"]) / len(st["latencies"])) if st["latencies"] else None

            # Health classification
            if failed_tasks > 0 and success_rate < 80.0:
                health_state = "degraded"
            elif tot_tasks > 0 and not st["last_active"]:
                health_state = "active"
            else:
                health_state = "healthy"

            agent_metrics.append(
                AgentHealthMetric(
                    agent_id=f"ag_{name.lower().replace(' ', '_')}",
                    name=name,
                    role=cfg.get("role", "Specialist Agent"),
                    provider=cfg.get("provider"),
                    model=cfg.get("model"),
                    status=health_state,
                    tasks_assigned=tot_tasks,
                    tasks_completed=completed_tasks,
                    tasks_failed=failed_tasks,
                    tools_executed=st["tools_executed"],
                    tool_failures=st["tool_failures"],
                    reworks_count=st["reworks_count"],
                    success_rate=round(success_rate, 1),
                    average_latency_ms=round(avg_lat, 1) if avg_lat is not None else None,
                    last_active=st["last_active"],
                )
            )

        # 5. Diagnostic Insights (Factual data only)
        insights: list[HealthInsight] = []

        # Overall Reliability Insight
        if total_execs > 0:
            if exec_success_rate >= 90.0:
                insights.append(
                    HealthInsight(
                        id="ins_rel_success",
                        category="reliability",
                        level="success",
                        title="High Operational Reliability",
                        detail=f"Workforce completed {completed_execs} of {total_execs} execution run(s) with {exec_success_rate:.1f}% success rate.",
                        data_points={"total_execs": total_execs, "success_rate": exec_success_rate},
                    )
                )
            else:
                insights.append(
                    HealthInsight(
                        id="ins_rel_warn",
                        category="reliability",
                        level="warning",
                        title="Execution Interruptions Observed",
                        detail=f"{failed_execs} run(s) encountered failures or interruptions out of {total_execs} total runs.",
                        data_points={"failed_execs": failed_execs, "total_execs": total_execs},
                    )
                )

        # Tool Execution Insight
        if tool_calls_count > 0:
            if tool_failures_count == 0:
                insights.append(
                    HealthInsight(
                        id="ins_tool_healthy",
                        category="performance",
                        level="success",
                        title="Zero Tool Exceptions",
                        detail=f"All {tool_calls_count} specialized tool invocations executed cleanly with 0 exceptions.",
                        data_points={"tools_count": tool_calls_count, "error_rate": 0.0},
                    )
                )
            else:
                insights.append(
                    HealthInsight(
                        id="ins_tool_err",
                        category="performance",
                        level="warning",
                        title="Tool Exceptions Detected",
                        detail=f"{tool_failures_count} of {tool_calls_count} tool calls failed ({tool_error_rate:.1f}% failure rate).",
                        data_points={"tool_failures": tool_failures_count, "error_rate": tool_error_rate},
                    )
                )

        # Quality Gate / Rework Insight
        if total_reworks > 0:
            insights.append(
                HealthInsight(
                    id="ins_rework_active",
                    category="quality",
                    level="warning",
                    title="Automated Quality Gate Rework",
                    detail=f"Reviewer triggered {total_reworks} rework cycle(s) to guarantee deliverable standards before acceptance.",
                    data_points={"rework_count": total_reworks},
                )
            )
        elif total_milestones > 0 and completed_milestones > 0:
            insights.append(
                HealthInsight(
                    id="ins_rework_clean",
                    category="quality",
                    level="info",
                    title="First-Pass Quality Compliance",
                    detail="All deliverable validations and milestone criteria passed on initial evaluation without rework loops.",
                    data_points={"rework_count": 0},
                )
            )

        # Overall Status
        if failed_execs > 0 or tool_error_rate > 20.0:
            overall_status = "degraded"
        elif total_execs > 0 and completed_execs < total_execs:
            overall_status = "active"
        else:
            overall_status = "healthy"

        return WorkforceHealthSummary(
            team_name=resolved_team,
            scope=scope,
            mission_id=mission_id,
            execution_id=execution_id,
            overall_status=overall_status,
            total_executions=total_execs,
            completed_executions=completed_execs,
            failed_executions=failed_execs,
            execution_success_rate=round(exec_success_rate, 1),
            total_milestones=total_milestones,
            completed_milestones=completed_milestones,
            milestone_success_rate=round(milestone_success_rate, 1),
            total_tools_executed=tool_calls_count,
            tool_failures=tool_failures_count,
            tool_error_rate=round(tool_error_rate, 1),
            rework_count=total_reworks,
            rework_rate=round(rework_rate, 1),
            approvals_count=approvals_count,
            average_execution_duration_sec=round(avg_exec_dur, 1),
            average_milestone_duration_sec=round(avg_ms_dur, 1),
            agents=agent_metrics,
            insights=insights,
        )

    analyze_health = analyze

    def _fetch_activities_for_executions(
        self,
        execution_ids: set[str],
        mission_id: str | None,
    ) -> list[dict[str, Any]]:
        """Fetches raw conversation activities matching the target executions."""
        results: list[dict[str, Any]] = []
        try:
            with self.store._get_connection() as conn:
                query = """
                    SELECT id, conversation_id, agent, activity_type, message, metadata, created_at
                    FROM conversation_activities
                    ORDER BY created_at ASC
                """
                rows = conn.execute(query).fetchall()

            for r in rows:
                meta = {}
                if r["metadata"]:
                    try:
                        meta = json.loads(r["metadata"]) if isinstance(r["metadata"], str) else dict(r["metadata"])
                    except Exception:
                        meta = {}

                act_exec = meta.get("execution_id")
                if execution_ids:
                    if act_exec and act_exec in execution_ids:
                        results.append({
                            "id": r["id"],
                            "agent": r["agent"],
                            "activity_type": r["activity_type"],
                            "message": r["message"],
                            "metadata": meta,
                            "created_at": r["created_at"],
                        })
                    elif not act_exec and mission_id and (r["conversation_id"] == f"conv_{mission_id}"):
                        results.append({
                            "id": r["id"],
                            "agent": r["agent"],
                            "activity_type": r["activity_type"],
                            "message": r["message"],
                            "metadata": meta,
                            "created_at": r["created_at"],
                        })
                else:
                    results.append({
                        "id": r["id"],
                        "agent": r["agent"],
                        "activity_type": r["activity_type"],
                        "message": r["message"],
                        "metadata": meta,
                        "created_at": r["created_at"],
                    })
        except Exception as exc:
            logger.debug("Failed to query activities for health: %s", exc)

        return results

    def _resolve_known_agents(self, team_name: str) -> dict[str, dict[str, Any]]:
        """Extracts agent definitions from the team configuration if available."""
        known: dict[str, dict[str, Any]] = {}
        if self.team_resolver:
            try:
                team = self.team_resolver(team_name)
                if team and hasattr(team, "agents"):
                    for a in team.agents:
                        known[a.name] = {
                            "role": getattr(a, "role", "Specialist Agent"),
                            "provider": getattr(a, "provider", None),
                            "model": getattr(a, "model", None),
                        }
            except Exception:
                pass
        return known
