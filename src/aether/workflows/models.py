"""
Domain models for Visual Workflow Builder.
Defines Triggers -> Agents -> Tools -> Approvals -> Deliverables visual DAG nodes and edges.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any
import uuid


class WorkflowNodeType(str, Enum):
    """Semantic categories for visual workflow nodes."""
    TRIGGER = "trigger"          # Schedule (cron/interval), file watcher, webhook, manual
    AGENT = "agent"              # Assigned digital worker / role with prompt template
    TOOL = "tool"                # Bound action / connector execution (github, files, calendar)
    APPROVAL = "approval"        # Operator clearance checkpoint / autopilot gate
    DELIVERABLE = "deliverable"  # Output target (dossier artifact, markdown report, notify)


@dataclass
class WorkflowNode:
    """A single functional block in the visual workflow canvas."""
    id: str
    type: WorkflowNodeType
    title: str
    config: dict[str, Any] = field(default_factory=dict)
    position: dict[str, float] = field(default_factory=lambda: {"x": 100.0, "y": 100.0})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value if hasattr(self.type, "value") else str(self.type),
            "title": self.title,
            "config": dict(self.config),
            "position": dict(self.position),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowNode:
        raw_type = data.get("type", "agent")
        try:
            node_type = WorkflowNodeType(raw_type)
        except ValueError:
            node_type = WorkflowNodeType.AGENT

        return cls(
            id=data.get("id") or f"node_{uuid.uuid4().hex[:6]}",
            type=node_type,
            title=data.get("title") or "Node",
            config=dict(data.get("config") or {}),
            position=dict(data.get("position") or {"x": 100.0, "y": 100.0}),
        )


@dataclass
class WorkflowEdge:
    """A directed dependency between two workflow nodes."""
    id: str
    source: str  # source node id
    target: str  # target node id
    condition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "condition": self.condition,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowEdge:
        return cls(
            id=data.get("id") or f"edge_{uuid.uuid4().hex[:6]}",
            source=data["source"],
            target=data["target"],
            condition=data.get("condition"),
        )


@dataclass
class WorkflowGraph:
    """The complete DAG topology of a visual workflow."""
    nodes: list[WorkflowNode] = field(default_factory=list)
    edges: list[WorkflowEdge] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowGraph:
        nodes = [WorkflowNode.from_dict(n) for n in data.get("nodes", [])]
        edges = [WorkflowEdge.from_dict(e) for e in data.get("edges", [])]
        return cls(nodes=nodes, edges=edges)


@dataclass
class Workflow:
    """A persisted visual workflow blueprint ready for compilation and execution."""
    id: str
    name: str
    workspace_id: str = "default"
    description: str = ""
    graph: WorkflowGraph = field(default_factory=WorkflowGraph)
    compiled_mission_id: str | None = None
    compiled_automation_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "name": self.name,
            "description": self.description,
            "graph": self.graph.to_dict(),
            "compiled_mission_id": self.compiled_mission_id,
            "compiled_automation_id": self.compiled_automation_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workflow:
        graph_data = data.get("graph") or {}
        if isinstance(graph_data, str):
            try:
                graph_data = json.loads(graph_data)
            except Exception:
                graph_data = {}

        return cls(
            id=data.get("id") or f"wf_{uuid.uuid4().hex[:8]}",
            workspace_id=data.get("workspace_id", "default"),
            name=data.get("name", "Untitled Workflow"),
            description=data.get("description", ""),
            graph=WorkflowGraph.from_dict(graph_data),
            compiled_mission_id=data.get("compiled_mission_id"),
            compiled_automation_id=data.get("compiled_automation_id"),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )
