"""
WorkflowCompiler: Translates visual workflow DAG graphs (Triggers -> Agents -> Tools -> Approvals -> Deliverables)
into real executable Missions with durable Milestones or Automations with Triggers and Pipeline Steps.
"""
from __future__ import annotations

from collections import defaultdict, deque
import logging
from typing import Any
import uuid

from aether.automation.models import (
    AutomationDefinition,
    OutputDestination,
    OutputType,
    PipelineStep,
    TriggerConfig,
    TriggerType,
)
from aether.missions.models import Deliverable, Milestone, MilestoneStatus, Mission, MissionStatus
from aether.workflows.models import Workflow, WorkflowGraph, WorkflowNode, WorkflowNodeType

logger = logging.getLogger(__name__)


class WorkflowValidationError(Exception):
    """Raised when a workflow graph contains structural or dependency errors."""
    pass


class WorkflowCompiler:
    """Validates and compiles visual workflow blueprints into executable runtime structures."""

    @classmethod
    def validate(cls, graph: WorkflowGraph) -> list[str]:
        """Validates graph structure, cycle-freedom, and node connectivity."""
        errors: list[str] = []
        if not graph.nodes:
            errors.append("Workflow graph must contain at least one node.")
            return errors

        node_ids = set()
        for n in graph.nodes:
            if n.id in node_ids:
                errors.append(f"Duplicate node ID detected: '{n.id}'.")
            node_ids.add(n.id)

        # Validate edges
        adj = defaultdict(list)
        in_degree = defaultdict(int)
        for n in graph.nodes:
            in_degree[n.id] = 0

        for e in graph.edges:
            if e.source not in node_ids:
                errors.append(f"Edge source '{e.source}' does not exist in nodes.")
            if e.target not in node_ids:
                errors.append(f"Edge target '{e.target}' does not exist in nodes.")
            adj[e.source].append(e.target)
            in_degree[e.target] += 1

        # Cycle detection via Kahn's algorithm
        queue = deque([nid for nid in node_ids if in_degree[nid] == 0])
        visited_count = 0
        while queue:
            curr = queue.popleft()
            visited_count += 1
            for nxt in adj[curr]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        if visited_count < len(node_ids):
            errors.append("Circular dependency (cycle) detected in workflow graph. Graph must be a valid DAG.")

        return errors

    @classmethod
    def topological_sort(cls, graph: WorkflowGraph) -> list[WorkflowNode]:
        """Returns nodes in topological dependency order."""
        errors = cls.validate(graph)
        if errors:
            raise WorkflowValidationError(f"Invalid workflow graph: {'; '.join(errors)}")

        nodes_by_id = {n.id: n for n in graph.nodes}
        adj = defaultdict(list)
        in_degree = {n.id: 0 for n in graph.nodes}

        for e in graph.edges:
            adj[e.source].append(e.target)
            in_degree[e.target] += 1

        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        ordered: list[WorkflowNode] = []

        while queue:
            curr = queue.popleft()
            ordered.append(nodes_by_id[curr])
            for nxt in adj[curr]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        return ordered

    @classmethod
    def compile_to_mission(
        cls,
        workflow: Workflow,
        store: Any,
        params: dict[str, Any] | None = None,
    ) -> Mission:
        """
        Compiles the visual workflow graph into an executable Mission with durable Milestones.
        Connects incoming edges as milestone dependencies and translates Approvals into checkpoints.
        """
        errors = cls.validate(workflow.graph)
        if errors:
            raise WorkflowValidationError(f"Workflow compilation failed: {'; '.join(errors)}")

        incoming_edges: dict[str, list[str]] = defaultdict(list)
        for e in workflow.graph.edges:
            incoming_edges[e.target].append(e.source)

        ordered_nodes = cls.topological_sort(workflow.graph)

        mission_id = f"msn-wf-{uuid.uuid4().hex[:8]}"
        milestones: list[Milestone] = []
        deliverables: list[Deliverable] = []
        node_to_milestone_id: dict[str, str] = {}

        for node in ordered_nodes:
            # Skip trigger node for Mission milestones (trigger initiates the mission)
            if node.type == WorkflowNodeType.TRIGGER:
                continue

            msn_id = f"ms-{uuid.uuid4().hex[:6]}-{node.id}"
            node_to_milestone_id[node.id] = msn_id

            # Map dependencies
            deps = [
                node_to_milestone_id[dep_node_id]
                for dep_node_id in incoming_edges[node.id]
                if dep_node_id in node_to_milestone_id
            ]

            meta = dict(node.config)
            meta["workflow_node_id"] = node.id
            meta["workflow_node_type"] = node.type.value

            agent_name = node.config.get("agent_name", "WorkflowExecutor")
            desc = node.config.get("prompt") or node.config.get("description") or f"Execute {node.title}"

            if node.type == WorkflowNodeType.APPROVAL:
                meta["is_checkpoint"] = True
                meta["approval_tier"] = node.config.get("tier", "supervised")
                desc = f"Human Clearance Gate: {node.title}"
                agent_name = "HumanOperator"

            elif node.type == WorkflowNodeType.DELIVERABLE:
                meta["is_deliverable"] = True
                meta["output_format"] = node.config.get("output_format", "markdown")
                desc = f"Produce Deliverable Artifact: {node.title}"
                d_path = node.config.get("target") or node.config.get("target_path") or f"artifacts/{node.title.lower().replace(' ', '_')}.md"
                deliverables.append(
                    Deliverable(
                        id=f"deliv-{uuid.uuid4().hex[:6]}-{node.id}",
                        mission_id=mission_id,
                        name=node.title,
                        path=d_path,
                        type="document",
                    )
                )

            elif node.type == WorkflowNodeType.TOOL:
                meta["is_tool_action"] = True
                meta["tool_id"] = node.config.get("tool_id", "")
                meta["tool_params"] = node.config.get("params", {})
                desc = f"Execute Tool Action: {node.config.get('tool_id', node.title)}"

            milestones.append(
                Milestone(
                    id=msn_id,
                    mission_id=mission_id,
                    title=node.title,
                    description=desc,
                    assigned_agent=agent_name,
                    dependencies=deps,
                    status=MilestoneStatus.PENDING,
                    metadata=meta,
                )
            )

        mission = Mission(
            id=mission_id,
            title=workflow.name,
            objective=workflow.description or f"Workflow execution of {workflow.name}",
            milestones=milestones,
            deliverables=deliverables,
            status=MissionStatus.READY,
            workspace_id=workflow.workspace_id or "default",
            team_name="Workflow Workforce",
            metadata={
                "workflow_id": workflow.id,
                "params": dict(params or {}),
                "compiled_from_visual_builder": True,
            },
        )

        store.save_mission(mission)
        workflow.compiled_mission_id = mission.id
        return mission

    @classmethod
    def compile_to_automation(
        cls,
        workflow: Workflow,
        store: Any,
    ) -> AutomationDefinition:
        """
        Compiles the visual workflow graph into an executable Automation daemon configuration.
        Maps triggers, pipeline steps, and output destinations.
        """
        errors = cls.validate(workflow.graph)
        if errors:
            raise WorkflowValidationError(f"Workflow compilation failed: {'; '.join(errors)}")

        incoming_edges: dict[str, list[str]] = defaultdict(list)
        for e in workflow.graph.edges:
            incoming_edges[e.target].append(e.source)

        ordered_nodes = cls.topological_sort(workflow.graph)

        trigger_cfg = TriggerConfig(type=TriggerType.MANUAL)
        steps: list[PipelineStep] = []
        out_dest: OutputDestination | None = None

        for node in ordered_nodes:
            if node.type == WorkflowNodeType.TRIGGER:
                t_type_raw = node.config.get("type", "manual")
                try:
                    t_type = TriggerType(t_type_raw)
                except ValueError:
                    t_type = TriggerType.MANUAL

                trigger_cfg = TriggerConfig(
                    type=t_type,
                    cron=node.config.get("cron"),
                    interval_seconds=node.config.get("interval_seconds"),
                    watch_path=node.config.get("watch_path"),
                    watch_pattern=node.config.get("watch_pattern", "*.*"),
                    watch_events=node.config.get("watch_events", ["created"]),
                    webhook_secret=node.config.get("webhook_secret"),
                    webhook_slug=node.config.get("webhook_slug"),
                )

            elif node.type in (WorkflowNodeType.AGENT, WorkflowNodeType.TOOL, WorkflowNodeType.APPROVAL):
                agent_name = node.config.get("agent_name", "Worker")
                prompt = node.config.get("prompt") or node.config.get("description") or "{input}"
                step_deps = incoming_edges[node.id]

                steps.append(
                    PipelineStep(
                        id=f"step_{node.id}",
                        name=node.title,
                        agent_name=agent_name,
                        prompt_template=prompt,
                        depends_on=[f"step_{d}" for d in step_deps],
                    )
                )

            elif node.type == WorkflowNodeType.DELIVERABLE:
                raw_out_type = node.config.get("output_type", "notification")
                try:
                    out_type = OutputType(raw_out_type)
                except ValueError:
                    out_type = OutputType.NOTIFICATION

                out_dest = OutputDestination(
                    type=out_type,
                    target_path=node.config.get("target_path"),
                    notify_title=node.title,
                )

        automation = AutomationDefinition(
            id=f"auto-wf-{uuid.uuid4().hex[:8]}",
            name=workflow.name,
            description=workflow.description,
            enabled=True,
            trigger=trigger_cfg,
            steps=steps,
            output_destination=out_dest,
            is_draft=False,
            requires_approval=any(n.type == WorkflowNodeType.APPROVAL for n in ordered_nodes),
            metadata={"workflow_id": workflow.id, "workspace_id": workflow.workspace_id, "compiled_from_visual_builder": True},
        )

        store.save_automation(automation)
        workflow.compiled_automation_id = automation.id
        return automation
