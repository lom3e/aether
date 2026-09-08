"""
Aether Replay ("Flight Recorder") Timeline Engine.
Compiles a chronological sequence of observable events from persisted SQLite
mission_executions, mission_execution_milestones, conversation_activities,
and mission_deliverables.
Zero Chain-of-Thought, zero private prompts, sanitized metadata only.
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

# Sensitive keys that must be stripped from any client-facing replay event
SENSITIVE_KEYS = {
    "thought", "thoughts", "reasoning", "prompt", "system_prompt", "private_reasoning", "chain_of_thought",
    "raw_response", "token", "secret", "api_key", "password", "auth", "auth_token", "api_secret",
    "hidden_instructions", "internal_thought", "scratchpad",
}

CREDENTIAL_INDICATORS = ("secret", "token", "password", "api_key", "auth")


def is_sensitive_reasoning_key(key: str) -> bool:
    k = str(key).lower()
    if k in {"thought", "thoughts", "reasoning", "prompt", "system_prompt", "private_reasoning", "chain_of_thought", "scratchpad", "internal_thought", "hidden_instructions"}:
        return True
    return any(s in k for s in ("chain_of_thought", "scratchpad"))


def is_credential_key(key: str) -> bool:
    k = str(key).lower()
    return any(c in k for c in CREDENTIAL_INDICATORS)


def sanitize_replay_data(data: Any, max_depth: int = 3) -> Any:
    """Recursively strips sensitive keys, masks credentials, and bounds payload sizes."""
    if max_depth <= 0:
        return "..."
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            key_str = str(k).lower()
            if is_sensitive_reasoning_key(key_str):
                continue
            if is_credential_key(key_str):
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = sanitize_replay_data(v, max_depth - 1)
        return cleaned
    elif isinstance(data, list):
        return [sanitize_replay_data(item, max_depth - 1) for item in data[:20]]
    elif isinstance(data, str) and len(data) > 500:
        return data[:500] + "... [truncated]"
    return data


@dataclass
class ReplayEvent:
    id: str
    seq: int
    timestamp: str
    event_type: str
    title: str
    description: str
    status: str  # "info", "success", "warning", "error"
    stage_name: str | None = None
    milestone_id: str | None = None
    agent: str | None = None
    task_id: str | None = None
    tool_name: str | None = None
    deliverable_id: str | None = None
    graph_node_id: str | None = None
    duration_ms: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayTimeline:
    mission_id: str
    mission_title: str
    execution_id: str
    run_number: int
    status: str
    started_at: str | None
    completed_at: str | None
    duration_seconds: float
    total_events: int
    events: list[ReplayEvent]

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        res["events"] = [e.to_dict() if hasattr(e, "to_dict") else e for e in self.events]
        return res


class ReplayCompiler:
    """
    Extracts, correlates, sanitizes, and assembles the chronological timeline of events
    for a specific execution run.
    """

    def __init__(self, store: MissionStore) -> None:
        self.store = store

    def compile(
        self,
        mission_id: str,
        execution_id: str | None = None,
    ) -> ReplayTimeline:
        """
        Compiles the full flight recorder timeline for the given mission and execution run.
        """
        mission = self.store.get_mission(mission_id, include_milestones=True)
        if not mission:
            raise ValueError(f"Mission {mission_id} not found.")

        # Resolve target execution
        if execution_id:
            execution = self.store.get_execution(execution_id)
        else:
            execution = self.store.get_active_execution(mission_id)
            if not execution:
                execs = self.store.list_executions(mission_id)
                execution = execs[0] if execs else None

        if not execution:
            # Pre-execution / Blueprint: return empty timeline
            now = datetime.now(timezone.utc).isoformat()
            return ReplayTimeline(
                mission_id=mission.id,
                mission_title=mission.title,
                execution_id="blueprint",
                run_number=0,
                status="blueprint",
                started_at=None,
                completed_at=None,
                duration_seconds=0.0,
                total_events=0,
                events=[],
            )

        # Milestone map for title lookups
        milestone_map = {m.id: m.title for m in mission.milestones}
        exec_milestones = self.store.get_execution_milestones(execution.id)
        for em in exec_milestones:
            if em.milestone_id not in milestone_map:
                milestone_map[em.milestone_id] = f"Stage {em.milestone_id[:6]}"

        events: list[ReplayEvent] = []
        raw_events: list[dict[str, Any]] = []

        # 1. Mission Started Event
        if execution.started_at:
            raw_events.append({
                "timestamp": execution.started_at,
                "event_type": "mission_started",
                "title": f"Mission Started: {mission.title}",
                "description": f"Execution Run #{execution.run_number} initialized with workforce: {execution.team_name or "Default Workforce"}.",
                "status": "info",
                "graph_node_id": f"exec_{execution.id}",
                "details": {
                    "run_number": execution.run_number,
                    "team_name": execution.team_name,
                    "objective": mission.objective[:200],
                },
            })

        # 2. Extract conversation activities
        conv_ids = [f"conv_{mission_id}", f"conv_{mission_id}_{execution.id}"]
        if mission.conversation_id:
            conv_ids.append(mission.conversation_id)

        acts = self._load_execution_activities(conv_ids, execution.id)
        for act in acts:
            mapped = self._map_activity_to_replay_event(act, milestone_map, execution.id)
            if mapped:
                raw_events.append(mapped)

        # 3. Execution Milestones lifecycle events
        for em in exec_milestones:
            m_title = milestone_map.get(em.milestone_id, "Stage")
            if em.started_at and not any(e.get("event_type") == "milestone_started" and e.get("milestone_id") == em.milestone_id for e in raw_events):
                raw_events.append({
                    "timestamp": em.started_at,
                    "event_type": "milestone_started",
                    "title": f"Stage Started: {m_title}",
                    "description": f"Milestone '{m_title}' began execution.",
                    "status": "info",
                    "milestone_id": em.milestone_id,
                    "stage_name": m_title,
                    "graph_node_id": f"milestone_{em.milestone_id}",
                    "details": {"status": em.status.value},
                })
            if em.completed_at and not any(e.get("event_type") == "milestone_completed" and e.get("milestone_id") == em.milestone_id for e in raw_events):
                st_val = "success" if em.status.value == "completed" else "error"
                raw_events.append({
                    "timestamp": em.completed_at,
                    "event_type": "milestone_completed",
                    "title": f"Stage Completed: {m_title}",
                    "description": f"Milestone '{m_title}' concluded with status: {em.status.value}.",
                    "status": st_val,
                    "milestone_id": em.milestone_id,
                    "stage_name": m_title,
                    "graph_node_id": f"milestone_{em.milestone_id}",
                    "details": {"status": em.status.value, "rework_count": getattr(em, "rework_count", 0)},
                })

        # 4. Deliverables Harvested Events
        deliverables = self.store.list_deliverables(mission_id, execution_id=execution.id)
        for d in deliverables:
            if not any(e.get("event_type") == "deliverable_harvested" and e.get("deliverable_id") == d.id for e in raw_events):
                st = "success" if d.status == "verified" else ("warning" if d.status == "rejected" else "info")
                m_name = milestone_map.get(d.milestone_id, "Mission Workflow") if d.milestone_id else "Mission Workflow"
                raw_events.append({
                    "timestamp": d.created_at,
                    "event_type": "deliverable_harvested",
                    "title": f"Deliverable Produced: {d.name}",
                    "description": f"Artifact '{d.name}' ({d.type}, {d.size_bytes} B) registered in stage '{m_name}'.",
                    "status": st,
                    "milestone_id": d.milestone_id,
                    "stage_name": m_name,
                    "deliverable_id": d.id,
                    "graph_node_id": f"deliv_{d.id}",
                    "details": {
                        "name": d.name,
                        "path": d.path,
                        "size_bytes": d.size_bytes,
                        "status": d.status,
                        "reviewer": (d.metadata or {}).get("reviewer_agent"),
                        "quality_score": (d.metadata or {}).get("quality_score"),
                    },
                })

        # 5. Mission Completed / Interrupted Event
        if execution.completed_at or execution.interrupted_at:
            t_end = execution.completed_at or execution.interrupted_at
            st = "success" if execution.status.value == "completed" else "error"
            desc = f"Execution Run #{execution.run_number} finished in {execution.duration_seconds:.1f}s with status '{execution.status.value}'."
            if execution.error_message:
                desc += f" Error: {execution.error_message}"
            raw_events.append({
                "timestamp": t_end,
                "event_type": "mission_completed" if execution.status.value == "completed" else "mission_interrupted",
                "title": f"Mission {execution.status.value.capitalize()}",
                "description": desc,
                "status": st,
                "graph_node_id": f"exec_{execution.id}",
                "details": {
                    "duration_seconds": execution.duration_seconds,
                    "final_status": execution.status.value,
                    "error": execution.error_message,
                },
            })

        # Sort chronologically by timestamp
        raw_events.sort(key=lambda x: str(x.get("timestamp") or ""))

        # Assemble sanitized ReplayEvents with sequence numbers
        for idx, re in enumerate(raw_events, start=1):
            events.append(
                ReplayEvent(
                    id=f"ev_{execution.id[:6]}_{idx:03d}",
                    seq=idx,
                    timestamp=re.get("timestamp") or execution.started_at or "",
                    event_type=re.get("event_type", "activity"),
                    title=re.get("title", "Execution Event"),
                    description=re.get("description", ""),
                    status=re.get("status", "info"),
                    stage_name=re.get("stage_name"),
                    milestone_id=re.get("milestone_id"),
                    agent=re.get("agent"),
                    task_id=re.get("task_id"),
                    tool_name=re.get("tool_name"),
                    deliverable_id=re.get("deliverable_id"),
                    graph_node_id=re.get("graph_node_id"),
                    duration_ms=re.get("duration_ms"),
                    details=sanitize_replay_data(re.get("details", {})),
                )
            )

        return ReplayTimeline(
            mission_id=mission.id,
            mission_title=mission.title,
            execution_id=execution.id,
            run_number=execution.run_number,
            status=execution.status.value,
            started_at=execution.started_at,
            completed_at=execution.completed_at or execution.interrupted_at,
            duration_seconds=execution.duration_seconds or 0.0,
            total_events=len(events),
            events=events,
        )

    compile_replay_timeline = compile

    def _load_execution_activities(
        self,
        conversation_ids: list[str],
        execution_id: str,
    ) -> list[dict[str, Any]]:
        """Loads activities from SQLite matching the given execution_id."""
        if not conversation_ids:
            return []
        results: list[dict[str, Any]] = []
        try:
            placeholders = ",".join("?" for _ in conversation_ids)
            query = f"""
                SELECT id, conversation_id, agent, activity_type, message, metadata, created_at
                FROM conversation_activities
                WHERE conversation_id IN ({placeholders})
                ORDER BY created_at ASC
            """
            with self.store._get_connection() as conn:
                rows = conn.execute(query, tuple(conversation_ids)).fetchall()

            for r in rows:
                meta = {}
                if r["metadata"]:
                    try:
                        meta = json.loads(r["metadata"]) if isinstance(r["metadata"], str) else dict(r["metadata"])
                    except Exception:
                        meta = {}

                # Strict execution isolation
                act_exec = meta.get("execution_id")
                if act_exec and act_exec != execution_id:
                    continue

                results.append({
                    "id": r["id"],
                    "conversation_id": r["conversation_id"],
                    "agent": r["agent"],
                    "activity_type": r["activity_type"],
                    "message": r["message"],
                    "metadata": meta,
                    "created_at": r["created_at"],
                })
        except Exception as exc:
            logger.debug("Failed to query execution activities: %s", exc)

        return results

    def _map_activity_to_replay_event(
        self,
        act: dict[str, Any],
        milestone_map: dict[str, str],
        execution_id: str,
    ) -> dict[str, Any] | None:
        """Translates an activity record into a clean, human-readable timeline event."""
        act_type = act.get("activity_type", "")
        agent = act.get("agent")
        msg = act.get("message") or ""
        meta = act.get("metadata") or {}
        created_at = act.get("created_at") or ""
        milestone_id = meta.get("milestone_id")
        stage_name = milestone_map.get(milestone_id) if milestone_id else None

        # Determine event mapping
        if "tool" in act_type:
            tool_name = meta.get("tool_name") or meta.get("tool") or "tool"
            tool_call_id = meta.get("tool_call_id") or act["id"]
            is_err = meta.get("is_error", False) or "error" in act_type.lower()
            return {
                "timestamp": created_at,
                "event_type": "tool_executed" if not is_err else "tool_failed",
                "title": f"Tool Invocated: {tool_name}" if not is_err else f"Tool Failed: {tool_name}",
                "description": f"Agent '{agent or "System"}' executed tool '{tool_name}': {msg[:180]}",
                "status": "error" if is_err else "info",
                "agent": agent,
                "tool_name": tool_name,
                "milestone_id": milestone_id,
                "stage_name": stage_name,
                "graph_node_id": f"tool_{tool_call_id}",
                "duration_ms": meta.get("duration_ms"),
                "details": {
                    "tool": tool_name,
                    "arguments": meta.get("arguments") or meta.get("input"),
                    "output_preview": meta.get("output_preview") or meta.get("result"),
                },
            }

        elif "quality_gate" in act_type:
            score = meta.get("quality_score") or meta.get("score")
            passed = meta.get("passed", True) if "failed" not in act_type else False
            reviewer = meta.get("reviewer_agent") or agent or "Reviewer"
            return {
                "timestamp": created_at,
                "event_type": "quality_gate_evaluated",
                "title": f"Quality Gate Passed ({score}/100)" if passed else "Quality Gate Rejected",
                "description": f"Reviewer '{reviewer}' evaluated deliverables with score {score}/100.",
                "status": "success" if passed else "warning",
                "agent": reviewer,
                "milestone_id": milestone_id,
                "stage_name": stage_name,
                "graph_node_id": f"agent_{reviewer}",
                "details": {
                    "reviewer": reviewer,
                    "score": score,
                    "rules": meta.get("rules"),
                },
            }

        elif "rework" in act_type:
            target_agent = meta.get("target_agent") or "Specialist"
            reason = meta.get("reason") or msg or "Quality gate standards not met."
            return {
                "timestamp": created_at,
                "event_type": "rework_dispatched",
                "title": f"Rework Dispatched to {target_agent}",
                "description": f"Defects identified. Corrective rework assigned to '{target_agent}': {reason[:160]}",
                "status": "warning",
                "agent": target_agent,
                "milestone_id": milestone_id,
                "stage_name": stage_name,
                "graph_node_id": f"agent_{target_agent}",
                "details": {"reason": reason, "target_agent": target_agent},
            }

        elif "approval" in act_type:
            is_granted = "granted" in act_type or meta.get("decision") == "approve"
            return {
                "timestamp": created_at,
                "event_type": "approval_granted" if is_granted else "approval_required",
                "title": "Human Approval Granted" if is_granted else "Approval Required",
                "description": f"Milestone '{stage_name or "Stage"}': {msg[:180]}",
                "status": "success" if is_granted else "warning",
                "milestone_id": milestone_id,
                "stage_name": stage_name,
                "graph_node_id": f"milestone_{milestone_id}" if milestone_id else None,
                "details": {"decision": meta.get("decision"), "notes": meta.get("notes")},
            }

        elif "deliverable" in act_type:
            d_name = meta.get("name") or meta.get("path") or "Artifact"
            d_id = meta.get("deliverable_id") or act["id"]
            return {
                "timestamp": created_at,
                "event_type": "deliverable_harvested",
                "title": f"Deliverable Harvested: {d_name}",
                "description": f"Agent '{agent or "Workforce"}' finalized artifact '{d_name}'.",
                "status": "success",
                "agent": agent,
                "milestone_id": milestone_id,
                "stage_name": stage_name,
                "deliverable_id": d_id,
                "graph_node_id": f"deliv_{d_id}",
                "details": {"name": d_name, "path": meta.get("path")},
            }

        elif "task" in act_type or "agent" in act_type:
            return {
                "timestamp": created_at,
                "event_type": "agent_action",
                "title": f"Agent Action: {agent or "Specialist"}",
                "description": msg[:200] or f"Specialist '{agent}' performed operations in stage '{stage_name or "Mission"}'.",
                "status": "info",
                "agent": agent,
                "milestone_id": milestone_id,
                "stage_name": stage_name,
                "graph_node_id": f"agent_{agent}" if agent else None,
                "details": {"message": msg[:200]},
            }

        # Generic activity fallback
        return {
            "timestamp": created_at,
            "event_type": act_type or "activity",
            "title": f"Activity: {agent or "System"}",
            "description": msg[:200],
            "status": "info",
            "agent": agent,
            "milestone_id": milestone_id,
            "stage_name": stage_name,
            "graph_node_id": f"agent_{agent}" if agent else None,
            "details": meta,
        }
