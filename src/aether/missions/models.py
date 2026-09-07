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


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


class MilestoneExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(slots=True)
class ExecutionMilestone:
    id: str
    execution_id: str
    milestone_id: str
    status: MilestoneExecutionStatus = MilestoneExecutionStatus.PENDING
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float = 0.0
    error: str | None = None
    output: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "execution_id": self.execution_id,
            "milestone_id": self.milestone_id,
            "status": self.status.value if isinstance(self.status, MilestoneExecutionStatus) else str(self.status),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "output": self.output,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionMilestone:
        status_raw = data.get("status", "pending")
        try:
            status = MilestoneExecutionStatus(status_raw)
        except ValueError:
            status = MilestoneExecutionStatus.PENDING

        return cls(
            id=data.get("id") or uuid.uuid4().hex,
            execution_id=data.get("execution_id", ""),
            milestone_id=data.get("milestone_id", ""),
            status=status,
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            error=data.get("error"),
            output=data.get("output"),
            metadata=data.get("metadata") or {},
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(slots=True)
class MissionExecution:
    id: str
    mission_id: str
    run_number: int
    status: ExecutionStatus = ExecutionStatus.PENDING
    current_milestone_id: str | None = None
    team_name: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None
    interrupted_at: str | None = None
    duration_seconds: float = 0.0
    error_message: str | None = None
    error_details: str | None = None
    lease_owner: str | None = None
    lease_expires_at: str | None = None
    heartbeat_at: str | None = None
    recovery_state: str = "none"
    pending_approval: dict[str, Any] | None = None
    approval_history: list[dict[str, Any]] = field(default_factory=list)
    milestone_states: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mission_id": self.mission_id,
            "run_number": self.run_number,
            "status": self.status.value if isinstance(self.status, ExecutionStatus) else str(self.status),
            "current_milestone_id": self.current_milestone_id,
            "team_name": self.team_name,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "interrupted_at": self.interrupted_at,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "error_details": self.error_details,
            "lease_owner": self.lease_owner,
            "lease_expires_at": self.lease_expires_at,
            "heartbeat_at": self.heartbeat_at,
            "recovery_state": self.recovery_state,
            "pending_approval": self.pending_approval,
            "approval_history": self.approval_history,
            "milestone_states": self.milestone_states,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MissionExecution:
        status_raw = data.get("status", "pending")
        try:
            status = ExecutionStatus(status_raw)
        except ValueError:
            status = ExecutionStatus.PENDING

        return cls(
            id=data.get("id") or uuid.uuid4().hex,
            mission_id=data.get("mission_id", ""),
            run_number=int(data.get("run_number", 1)),
            status=status,
            current_milestone_id=data.get("current_milestone_id"),
            team_name=data.get("team_name"),
            started_at=data.get("started_at") or datetime.now(timezone.utc).isoformat(),
            completed_at=data.get("completed_at"),
            interrupted_at=data.get("interrupted_at"),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            error_message=data.get("error_message"),
            error_details=data.get("error_details"),
            lease_owner=data.get("lease_owner"),
            lease_expires_at=data.get("lease_expires_at"),
            heartbeat_at=data.get("heartbeat_at"),
            recovery_state=data.get("recovery_state", "none"),
            pending_approval=data.get("pending_approval"),
            approval_history=data.get("approval_history") or [],
            milestone_states=data.get("milestone_states") or [],
            metadata=data.get("metadata") or {},
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )


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
    active_execution_id: str | None = None
    active_execution: MissionExecution | None = None
    milestones: list[Milestone] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "title": self.title,
            "objective": self.objective,
            "status": self.status.value if isinstance(self.status, MissionStatus) else str(self.status),
            "team_name": self.team_name,
            "conversation_id": self.conversation_id,
            "project_id": self.project_id,
            "active_execution_id": self.active_execution_id,
            "milestones": [m.to_dict() for m in self.milestones],
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.active_execution is not None:
            res["active_execution"] = self.active_execution.to_dict()
        return res

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

        active_exec = None
        if isinstance(data.get("active_execution"), dict):
            active_exec = MissionExecution.from_dict(data["active_execution"])

        return cls(
            id=data.get("id") or uuid.uuid4().hex,
            workspace_id=data.get("workspace_id", "default"),
            title=data.get("title", "New Mission"),
            objective=data.get("objective", ""),
            status=status,
            team_name=data.get("team_name"),
            conversation_id=data.get("conversation_id"),
            project_id=data.get("project_id"),
            active_execution_id=data.get("active_execution_id"),
            active_execution=active_exec,
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
    execution_id: str | None = None
    milestone_id: str | None = None
    sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mission_id": self.mission_id,
            "execution_id": self.execution_id,
            "milestone_id": self.milestone_id,
            "name": self.name,
            "path": self.path,
            "type": self.type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "status": self.status,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Deliverable:
        return cls(
            id=data.get("id") or uuid.uuid4().hex,
            mission_id=data.get("mission_id", ""),
            execution_id=data.get("execution_id"),
            milestone_id=data.get("milestone_id"),
            name=data.get("name", "Untitled Deliverable"),
            path=data.get("path", ""),
            type=data.get("type", "document"),
            size_bytes=int(data.get("size_bytes", 0)),
            sha256=data.get("sha256"),
            status=data.get("status", "draft"),
            metadata=data.get("metadata") or {},
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or data.get("created_at") or datetime.now(timezone.utc).isoformat(),
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
