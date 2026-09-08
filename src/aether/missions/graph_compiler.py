"""
Execution Graph Compiler.
Transforms real runtime execution states, milestones, observable activities,
and deliverables into deterministic, inspectable MissionGraph DAG models.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import re
import time
from typing import Any, TYPE_CHECKING

from aether.missions.models import (
    ExecutionStatus,
    GraphEdge,
    GraphNode,
    MilestoneStatus,
    Mission,
    MissionExecution,
    MissionGraph,
    MissionStatus,
)

if TYPE_CHECKING:
    from aether.missions.store import MissionStore

logger = logging.getLogger(__name__)

# Keys stripped from graph metadata to ensure zero chain-of-thought leaks
SENSITIVE_METADATA_KEYS = {
    "prompt",
    "system_prompt",
    "hidden_prompt",
    "raw_prompt",
    "raw_response",
    "chain_of_thought",
    "thought",
    "thinking",
    "private_reasoning",
    "reasoning",
    "token",
    "api_key",
    "password",
    "secret",
}


def sanitize_graph_metadata(meta: dict[str, Any] | None) -> dict[str, Any]:
    """
    Recursively sanitizes metadata dictionaries to guarantee chain-of-thought privacy
    and prevent secret leakage while preserving observable operational data.
    """
    if not meta or not isinstance(meta, dict):
        return {}

    clean: dict[str, Any] = {}
    for k, v in meta.items():
        k_lower = str(k).lower()
        if (
            k_lower in SENSITIVE_METADATA_KEYS
            or "prompt" in k_lower
            or "thought" in k_lower
            or "reasoning" in k_lower
            or "secret" in k_lower
        ):
            continue

        if isinstance(v, dict):
            clean[k] = sanitize_graph_metadata(v)
        elif isinstance(v, list):
            clean[k] = [
                sanitize_graph_metadata(item) if isinstance(item, dict) else item
                for item in v
                if not (isinstance(item, str) and len(item) > 1000)
            ]
        elif isinstance(v, str):
            clean[k] = v[:500] + "..." if len(v) > 500 else v
        elif isinstance(v, (int, float, bool, type(None))):
            clean[k] = v
        else:
            clean[k] = str(v)[:200]

    return clean


def slugify_id(value: str) -> str:
    """Converts display names into safe, deterministic graph identifiers."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip().lower())
    return cleaned.strip("_") or "unknown"


class ExecutionGraphCompiler:
    """
    Deterministic Execution Graph Compiler.
    Transforms persistent Mission, Execution, Milestone, Activity, and Deliverable records
    into an inspectable Directed Acyclic Graph (MissionGraph).
    """

    def __init__(self, store: MissionStore, cache_ttl_seconds: float = 2.0) -> None:
        self.store = store
        self.cache_ttl_seconds = cache_ttl_seconds
        # Key: (mission_id, execution_id) -> (cached_at_timestamp, MissionGraph)
        self._cache: dict[tuple[str, str | None], tuple[float, MissionGraph]] = {}

    def invalidate_cache(self, mission_id: str | None = None, execution_id: str | None = None) -> None:
        """Invalidates in-memory graph cache entries."""
        if mission_id is None and execution_id is None:
            self._cache.clear()
            return

        to_remove = []
        for (m_id, e_id) in self._cache.keys():
            if mission_id and m_id != mission_id:
                continue
            if execution_id and e_id != execution_id:
                continue
            to_remove.append((m_id, e_id))

        for key in to_remove:
            self._cache.pop(key, None)

    def compile(
        self,
        mission_id: str,
        execution_id: str | None = None,
        force_refresh: bool = False,
    ) -> MissionGraph | None:
        """
        Compiles the execution graph for the specified mission and optional execution run.

        If execution_id is specified:
            Strictly isolates and compiles the graph for that execution run.
        If execution_id is None:
            Defaults to the active execution (or latest execution if any exists).
            Falls back to the structural milestone blueprint if no executions exist yet.
        """
        mission = self.store.get_mission(mission_id, include_milestones=True)
        if not mission:
            return None

        # Resolve target execution
        target_exec: MissionExecution | None = None
        if execution_id:
            target_exec = self.store.get_execution(execution_id)
            if not target_exec or target_exec.mission_id != mission.id:
                # Execution requested does not belong to this mission
                return None
        else:
            if mission.active_execution_id:
                target_exec = self.store.get_execution(mission.active_execution_id)
            if not target_exec:
                executions = self.store.list_executions(mission.id)
                if executions:
                    target_exec = executions[-1]

        cache_key = (mission.id, target_exec.id if target_exec else None)

        # Check Cache: only reuse cache if target execution is in terminal state
        is_terminal = target_exec is not None and target_exec.status in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        )
        if not force_refresh and is_terminal and cache_key in self._cache:
            _, cached_graph = self._cache[cache_key]
            return cached_graph


        # Build Graph
        nodes: list[GraphNode] = []
        node_ids: set[str] = set()
        edges: list[GraphEdge] = []
        edge_ids: set[str] = set()

        def _add_node(node: GraphNode) -> bool:
            if node.id in node_ids:
                return False
            nodes.append(node)
            node_ids.add(node.id)
            return True

        def _add_edge(edge: GraphEdge) -> bool:
            if edge.id in edge_ids:
                return False
            # Strict edge integrity: source and target MUST exist in nodes
            if edge.source not in node_ids or edge.target not in node_ids:
                return False
            edges.append(edge)
            edge_ids.add(edge.id)
            return True

        # 1. Root Mission Node
        root_node_id = f"mission_{mission.id}"
        _add_node(
            GraphNode(
                id=root_node_id,
                type="mission",
                label=mission.title,
                status=mission.status.value if isinstance(mission.status, MissionStatus) else str(mission.status),
                metadata=sanitize_graph_metadata({
                    "objective": mission.objective,
                    "team_name": mission.team_name,
                    "project_id": mission.project_id,
                    "active_execution_id": mission.active_execution_id,
                    "created_at": mission.created_at,
                    "updated_at": mission.updated_at,
                }),
            )
        )

        # -----------------------------------------------------------------------
        # Case A: Structural Blueprint Mode (No Executions recorded yet)
        # -----------------------------------------------------------------------
        if target_exec is None:
            # Add Milestones
            for idx, m in enumerate(mission.milestones):
                m_node_id = f"milestone_{m.id}"
                m_status_val = m.status.value if isinstance(m.status, MilestoneStatus) else str(m.status)
                _add_node(
                    GraphNode(
                        id=m_node_id,
                        type="milestone",
                        label=m.title,
                        status=m_status_val,
                        metadata=sanitize_graph_metadata({
                            "milestone_id": m.id,
                            "order_idx": m.order_idx,
                            "description": m.description,
                            "dependencies": m.dependencies,
                            "completed_at": m.completed_at,
                        }),
                    )
                )

                # Containment edge from Mission to Milestone
                _add_edge(
                    GraphEdge(
                        id=f"edge_contain_{mission.id}_{m.id}",
                        source=root_node_id,
                        target=m_node_id,
                        type="contains",
                        label="contains",
                    )
                )

                # Dependency / sequential edges
                if m.dependencies:
                    for dep_id in m.dependencies:
                        _add_edge(
                            GraphEdge(
                                id=f"edge_dep_{dep_id}_{m.id}",
                                source=f"milestone_{dep_id}",
                                target=m_node_id,
                                type="depends_on",
                                label="depends_on",
                            )
                        )
                elif idx > 0:
                    prev_m = mission.milestones[idx - 1]
                    _add_edge(
                        GraphEdge(
                            id=f"edge_seq_{prev_m.id}_{m.id}",
                            source=f"milestone_{prev_m.id}",
                            target=m_node_id,
                            type="depends_on",
                            label="next",
                        )
                    )

            # Add Deliverables
            deliverables = self.store.list_deliverables(mission.id)
            for d in deliverables:
                d_node_id = f"deliverable_{d.id}"
                _add_node(
                    GraphNode(
                        id=d_node_id,
                        type="deliverable",
                        label=d.name,
                        status=d.status,
                        metadata=sanitize_graph_metadata(d.to_dict()),
                    )
                )
                source_id = f"milestone_{d.milestone_id}" if d.milestone_id and f"milestone_{d.milestone_id}" in node_ids else root_node_id
                _add_edge(
                    GraphEdge(
                        id=f"edge_del_{d.id}",
                        source=source_id,
                        target=d_node_id,
                        type="produced",
                        label="produced",
                    )
                )

            graph = MissionGraph(
                mission_id=mission.id,
                execution_id=None,
                nodes=nodes,
                edges=edges,
                metadata={
                    "mode": "blueprint",
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                    "compiled_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            return graph



        # -----------------------------------------------------------------------
        # Case B: Execution-Aware Graph Mode
        # -----------------------------------------------------------------------
        exec_node_id = f"execution_{target_exec.id}"
        exec_status_val = (
            target_exec.status.value
            if isinstance(target_exec.status, ExecutionStatus)
            else str(target_exec.status)
        )
        _add_node(
            GraphNode(
                id=exec_node_id,
                type="execution",
                label=f"Run #{target_exec.run_number}",
                status=exec_status_val,
                metadata=sanitize_graph_metadata({
                    "execution_id": target_exec.id,
                    "run_number": target_exec.run_number,
                    "team_name": target_exec.team_name,
                    "started_at": target_exec.started_at,
                    "completed_at": target_exec.completed_at,
                    "duration_seconds": target_exec.duration_seconds,
                    "error_message": target_exec.error_message,
                    "recovery_state": target_exec.recovery_state,
                    "rework_attempts": target_exec.metadata.get("rework_attempts", 0) if target_exec.metadata else 0,
                }),
            )
        )

        # Mission -> Execution edge
        _add_edge(
            GraphEdge(
                id=f"edge_has_exec_{mission.id}_{target_exec.id}",
                source=root_node_id,
                target=exec_node_id,
                type="has_execution",
                label=f"run #{target_exec.run_number}",
            )
        )

        # Fetch Milestone execution records
        exec_milestones = {
            em.milestone_id: em
            for em in self.store.get_execution_milestones(target_exec.id)
        }

        # Add Milestone Nodes for this execution
        for idx, m in enumerate(mission.milestones):
            m_node_id = f"milestone_{m.id}"
            exec_m = exec_milestones.get(m.id)
            if exec_m:
                m_status_val = (
                    exec_m.status.value
                    if hasattr(exec_m.status, "value")
                    else str(exec_m.status)
                )
                m_duration = exec_m.duration_seconds
                m_started = exec_m.started_at
                m_completed = exec_m.completed_at
                m_error = exec_m.error
            else:
                m_status_val = m.status.value if isinstance(m.status, MilestoneStatus) else str(m.status)
                m_duration = 0.0
                m_started = None
                m_completed = m.completed_at
                m_error = None

            _add_node(
                GraphNode(
                    id=m_node_id,
                    type="milestone",
                    label=m.title,
                    status=m_status_val,
                    metadata=sanitize_graph_metadata({
                        "milestone_id": m.id,
                        "execution_id": target_exec.id,
                        "order_idx": m.order_idx,
                        "description": m.description,
                        "dependencies": m.dependencies,
                        "started_at": m_started,
                        "completed_at": m_completed,
                        "duration_seconds": m_duration,
                        "error": m_error,
                    }),
                )
            )

            # Execution -> Milestone containment edge
            _add_edge(
                GraphEdge(
                    id=f"edge_exec_contains_{target_exec.id}_{m.id}",
                    source=exec_node_id,
                    target=m_node_id,
                    type="contains",
                    label="milestone",
                )
            )

            # Dependencies / sequential edges
            if m.dependencies:
                for dep_id in m.dependencies:
                    _add_edge(
                        GraphEdge(
                            id=f"edge_dep_{dep_id}_{m.id}",
                            source=f"milestone_{dep_id}",
                            target=m_node_id,
                            type="depends_on",
                            label="depends_on",
                        )
                    )
            elif idx > 0:
                prev_m = mission.milestones[idx - 1]
                _add_edge(
                    GraphEdge(
                        id=f"edge_seq_{prev_m.id}_{m.id}",
                        source=f"milestone_{prev_m.id}",
                        target=m_node_id,
                        type="depends_on",
                        label="next",
                    )
                )

        # 3. Query activities from conversation_activities strictly for this execution
        conv_ids = [cid for cid in [mission.conversation_id, f"conv_{mission.id}"] if cid]
        activities = self._query_execution_activities(conv_ids, target_exec.id)

        # Track participating agents & tool activities
        participating_agents: set[str] = set()
        active_milestone_agent_map: dict[str, str] = {}
        last_milestone_id = mission.milestones[-1].id if mission.milestones else None

        for act in activities:
            agent_name = act.get("agent")
            meta = act.get("metadata") or {}
            m_id = meta.get("milestone_id")

            if agent_name and agent_name.lower() not in ("system", "user", "unknown"):
                participating_agents.add(agent_name)
                if m_id:
                    active_milestone_agent_map[m_id] = agent_name

        # If team_name is defined and no agents observed yet, add team coordinator
        if not participating_agents and target_exec.team_name:
            participating_agents.add("Workforce Lead")

        # Add Agent Nodes
        for agent_name in sorted(participating_agents):
            agent_slug = slugify_id(agent_name)
            agent_node_id = f"agent_{agent_slug}"

            # Infer agent status
            agent_status = "idle"
            if target_exec.status == ExecutionStatus.RUNNING:
                agent_status = "running"
            elif target_exec.status == ExecutionStatus.COMPLETED:
                agent_status = "completed"
            elif target_exec.status == ExecutionStatus.FAILED:
                agent_status = "failed"

            _add_node(
                GraphNode(
                    id=agent_node_id,
                    type="agent",
                    label=agent_name,
                    status=agent_status,
                    metadata=sanitize_graph_metadata({
                        "agent_name": agent_name,
                        "execution_id": target_exec.id,
                        "team_name": target_exec.team_name,
                    }),
                )
            )

            # Attach agent to milestones where they acted, or to execution
            attached = False
            for m in mission.milestones:
                if active_milestone_agent_map.get(m.id) == agent_name:
                    _add_edge(
                        GraphEdge(
                            id=f"edge_delegated_{m.id}_{agent_slug}",
                            source=f"milestone_{m.id}",
                            target=agent_node_id,
                            type="delegated_to",
                            label="delegated_to",
                        )
                    )
                    attached = True

            if not attached:
                # Default delegation from current execution node
                _add_edge(
                    GraphEdge(
                        id=f"edge_exec_delegated_{target_exec.id}_{agent_slug}",
                        source=exec_node_id,
                        target=agent_node_id,
                        type="delegated_to",
                        label="delegated_to",
                    )
                )

        # 4. Add Stage Task Nodes for Milestones
        for m in mission.milestones:
            m_node_id = f"milestone_{m.id}"
            task_node_id = f"task_stage_{m.id}"
            exec_m = exec_milestones.get(m.id)
            task_status = exec_m.status.value if exec_m and hasattr(exec_m.status, "value") else (str(exec_m.status) if exec_m else "pending")

            _add_node(
                GraphNode(
                    id=task_node_id,
                    type="task",
                    label=f"Execute: {m.title}",
                    status=task_status,
                    metadata=sanitize_graph_metadata({
                        "milestone_id": m.id,
                        "execution_id": target_exec.id,
                        "description": m.description,
                    }),
                )
            )

            # Edge: assigned agent executes task, or milestone contains task
            assigned_agent = active_milestone_agent_map.get(m.id)
            if assigned_agent:
                agent_slug = slugify_id(assigned_agent)
                _add_edge(
                    GraphEdge(
                        id=f"edge_executes_{agent_slug}_{task_node_id}",
                        source=f"agent_{agent_slug}",
                        target=task_node_id,
                        type="executes",
                        label="executes",
                    )
                )
            else:
                _add_edge(
                    GraphEdge(
                        id=f"edge_milestone_task_{m.id}",
                        source=m_node_id,
                        target=task_node_id,
                        type="contains",
                        label="task",
                    )
                )

        # 5. Add Tool Execution Nodes
        for act in activities:
            if act.get("activity_type") == "tool_called":
                meta = act.get("metadata") or {}
                t_name = meta.get("tool_name", "tool")
                act_id = act.get("id") or f"tool_{len(nodes)}"
                tool_node_id = f"tool_{act_id}"

                _add_node(
                    GraphNode(
                        id=tool_node_id,
                        type="tool",
                        label=f"Tool: {t_name}",
                        status="completed",
                        metadata=sanitize_graph_metadata({
                            "tool_name": t_name,
                            "arguments": meta.get("arguments"),
                            "created_at": act.get("created_at"),
                            "execution_id": target_exec.id,
                            "milestone_id": meta.get("milestone_id"),
                        }),
                    )
                )

                # Connect Tool to Task or Agent
                target_milestone = meta.get("milestone_id")
                if target_milestone and f"task_stage_{target_milestone}" in node_ids:
                    source_task = f"task_stage_{target_milestone}"
                    _add_edge(
                        GraphEdge(
                            id=f"edge_invoked_{source_task}_{tool_node_id}",
                            source=source_task,
                            target=tool_node_id,
                            type="invoked",
                            label="invoked",
                        )
                    )
                else:
                    agent_name = act.get("agent") or "Workforce Lead"
                    agent_slug = slugify_id(agent_name)
                    if f"agent_{agent_slug}" in node_ids:
                        _add_edge(
                            GraphEdge(
                                id=f"edge_invoked_{agent_slug}_{tool_node_id}",
                                source=f"agent_{agent_slug}",
                                target=tool_node_id,
                                type="invoked",
                                label="invoked",
                            )
                        )

        # 6. Quality Gate & Reviewer Nodes
        last_gate = target_exec.metadata.get("last_quality_gate") if target_exec.metadata else None
        if last_gate and isinstance(last_gate, dict):
            reviewer_agent = last_gate.get("reviewer_agent", "Reviewer Agent")
            rev_slug = slugify_id(reviewer_agent)
            rev_agent_id = f"agent_{rev_slug}"

            _add_node(
                GraphNode(
                    id=rev_agent_id,
                    type="agent",
                    label=reviewer_agent,
                    status="completed" if target_exec.status == ExecutionStatus.COMPLETED else "idle",
                    metadata=sanitize_graph_metadata({
                        "agent_name": reviewer_agent,
                        "role": "Quality Gate Auditor",
                        "execution_id": target_exec.id,
                    }),
                )
            )

            gate_task_id = f"task_quality_gate_{target_exec.id}"
            score = last_gate.get("score", 0)
            passed = last_gate.get("passed", False)
            _add_node(
                GraphNode(
                    id=gate_task_id,
                    type="task",
                    label=f"Quality Gate ({score}/100)",
                    status="completed" if passed else "failed",
                    metadata=sanitize_graph_metadata({
                        "score": score,
                        "passed": passed,
                        "feedback": last_gate.get("feedback"),
                        "redlines": last_gate.get("redlines"),
                        "execution_id": target_exec.id,
                    }),
                )
            )

            _add_edge(
                GraphEdge(
                    id=f"edge_executes_{rev_slug}_{gate_task_id}",
                    source=rev_agent_id,
                    target=gate_task_id,
                    type="executes",
                    label="evaluates",
                )
            )

            if last_milestone_id and f"milestone_{last_milestone_id}" in node_ids:
                _add_edge(
                    GraphEdge(
                        id=f"edge_verifies_{last_milestone_id}_{gate_task_id}",
                        source=f"milestone_{last_milestone_id}",
                        target=gate_task_id,
                        type="verifies",
                        label="verifies",
                    )
                )

            # Rework cycles
            rework_count = target_exec.metadata.get("rework_attempts", 0)
            if rework_count and rework_count > 0:
                for attempt_idx in range(1, rework_count + 1):
                    rework_task_id = f"task_rework_{target_exec.id}_{attempt_idx}"
                    _add_node(
                        GraphNode(
                            id=rework_task_id,
                            type="task",
                            label=f"Rework Cycle #{attempt_idx}",
                            status="completed",
                            metadata=sanitize_graph_metadata({
                                "rework_attempt": attempt_idx,
                                "execution_id": target_exec.id,
                            }),
                        )
                    )
                    _add_edge(
                        GraphEdge(
                            id=f"edge_rework_{gate_task_id}_{rework_task_id}",
                            source=gate_task_id,
                            target=rework_task_id,
                            type="rework",
                            label="rework",
                        )
                    )

        # 7. Deliverables Nodes for this execution
        deliverables = self.store.list_deliverables(mission.id, execution_id=target_exec.id)
        for d in deliverables:
            d_node_id = f"deliverable_{d.id}"
            _add_node(
                GraphNode(
                    id=d_node_id,
                    type="deliverable",
                    label=d.name,
                    status=d.status,
                    metadata=sanitize_graph_metadata(d.to_dict()),
                )
            )

            # Link Deliverable to Milestone or Execution
            target_source = None
            if d.milestone_id and f"milestone_{d.milestone_id}" in node_ids:
                target_source = f"milestone_{d.milestone_id}"
            elif f"task_stage_{d.milestone_id}" in node_ids:
                target_source = f"task_stage_{d.milestone_id}"
            else:
                target_source = exec_node_id

            _add_edge(
                GraphEdge(
                    id=f"edge_del_{d.id}",
                    source=target_source,
                    target=d_node_id,
                    type="produced",
                    label="produced",
                )
            )

        graph = MissionGraph(
            mission_id=mission.id,
            execution_id=target_exec.id,
            nodes=nodes,
            edges=edges,
            metadata={
                "execution_id": target_exec.id,
                "run_number": target_exec.run_number,
                "execution_status": exec_status_val,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "compiled_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        if is_terminal:
            self._cache[cache_key] = (time.time(), graph)
        return graph


    def _query_execution_activities(
        self,
        conversation_ids: list[str],
        execution_id: str,
    ) -> list[dict[str, Any]]:
        """
        Loads observable activities from SQLite conversation_activities strictly filtered to
        the given execution_id.
        """
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
                try:
                    if r["metadata"]:
                        meta = json.loads(r["metadata"]) if isinstance(r["metadata"], str) else dict(r["metadata"])
                except Exception:
                    meta = {}

                # Strict execution isolation: include only if activity execution_id matches
                act_exec_id = meta.get("execution_id")
                if act_exec_id and act_exec_id != execution_id:
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
