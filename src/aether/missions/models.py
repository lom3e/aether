"""
Aether Missions Domain Models.
Defines Mission, Milestone, MissionStatus, MilestoneStatus, and Graph data structures.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid


class MissionStatus(StrEnum):
    DRAFT = "draft"
    PLANNING = "planning"
    RUNNING = "running"
    VERIFYING = "verifying"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class MilestoneStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class Milestone:
    id: str
    mission_id: str
    title: str
    description: str = ""
    status: MilestoneStatus = MilestoneStatus.PENDING
    order_idx: int = 0
    dependencies: list[str] = field(default_factory=list)
    completed_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mission_id": self.mission_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value if isinstance(self.status, MilestoneStatus) else str(self.status),
            "order_idx": self.order_idx,
            "dependencies": list(self.dependencies),
            "completed_at": self.completed_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Milestone:
        status_raw = data.get("status", "pending")
        try:
            status = MilestoneStatus(status_raw)
        except ValueError:
            status = MilestoneStatus.PENDING

        raw_deps = data.get("dependencies") or []
        deps = list(raw_deps) if isinstance(raw_deps, (list, tuple)) else []

        return cls(
            id=data.get("id") or uuid.uuid4().hex,
            mission_id=data["mission_id"],
            title=data.get("title", "Untitled Milestone"),
            description=data.get("description", ""),
            status=status,
            order_idx=int(data.get("order_idx", 0)),
            dependencies=deps,
            completed_at=data.get("completed_at"),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(slots=True)
class Mission:
    id: str
    workspace_id: str
    title: str
    objective: str
    status: MissionStatus = MissionStatus.DRAFT
    team_name: str | None = None
    conversation_id: str | None = None
    project_id: str | None = None
    milestones: list[Milestone] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "title": self.title,
            "objective": self.objective,
            "status": self.status.value if isinstance(self.status, MissionStatus) else str(self.status),
            "team_name": self.team_name,
            "conversation_id": self.conversation_id,
            "project_id": self.project_id,
            "milestones": [m.to_dict() for m in self.milestones],
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Mission:
        status_raw = data.get("status", "draft")
        try:
            status = MissionStatus(status_raw)
        except ValueError:
            status = MissionStatus.DRAFT

        raw_milestones = data.get("milestones") or []
        milestones = [
            Milestone.from_dict(m) if isinstance(m, dict) else m
            for m in raw_milestones
        ]

        return cls(
            id=data.get("id") or uuid.uuid4().hex,
            workspace_id=data.get("workspace_id", "default"),
            title=data.get("title", "New Mission"),
            objective=data.get("objective", ""),
            status=status,
            team_name=data.get("team_name"),
            conversation_id=data.get("conversation_id"),
            project_id=data.get("project_id"),
            milestones=milestones,
            metadata=data.get("metadata") or {},
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(slots=True)
class Deliverable:
    id: str
    mission_id: str
    name: str
    path: str
    type: str = "document"  # "document", "code", "data", "archive"
    size_bytes: int = 0
    status: str = "draft"  # "verified", "draft", "final"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mission_id": self.mission_id,
            "name": self.name,
            "path": self.path,
            "type": self.type,
            "size_bytes": self.size_bytes,
            "status": self.status,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Deliverable:
        return cls(
            id=data.get("id") or uuid.uuid4().hex,
            mission_id=data.get("mission_id", ""),
            name=data.get("name", "Untitled Deliverable"),
            path=data.get("path", ""),
            type=data.get("type", "document"),
            size_bytes=int(data.get("size_bytes", 0)),
            status=data.get("status", "draft"),
            metadata=data.get("metadata") or {},
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(slots=True)
class GraphNode:
    id: str
    type: str  # "mission", "milestone", "task", "agent", "tool", "deliverable"
    label: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "status": self.status,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class GraphEdge:
    id: str
    source: str
    target: str
    type: str  # "contains", "depends_on", "produced", "delegated_to"
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "label": self.label,
        }


@dataclass(slots=True)
class MissionGraph:
    mission_id: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }
