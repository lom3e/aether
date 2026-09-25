"""
Domain models for Aether Operational Autonomy ("Aether, take care of it").
Defines goals, lifecycle stages, autonomous plans, and execution statuses.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid


class AutonomousGoalStatus(StrEnum):
    PLANNING = "planning"
    PENDING_APPROVAL = "pending_approval"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def from_str(cls, val: str) -> AutonomousGoalStatus:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.PLANNING


class AutonomousStageType(StrEnum):
    UNDERSTAND = "understand"
    PLAN = "plan"
    ALLOCATE_RESOURCES = "allocate_resources"
    WORKFORCE_DISPATCH = "workforce_dispatch"
    ACTION_EXECUTION = "action_execution"
    SAFETY_VERIFICATION = "safety_verification"
    DELIVERABLE_CREATION = "deliverable_creation"
    NOTIFICATION = "notification"
    LEARNING_REFLECTION = "learning_reflection"

    @classmethod
    def from_str(cls, val: str) -> AutonomousStageType:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.UNDERSTAND


@dataclass(slots=True)
class AutonomousStage:
    """A granular stage within an autonomous goal execution plan."""
    id: str
    stage_type: AutonomousStageType
    title: str
    status: str = "pending"  # pending, running, completed, waiting_approval, failed, skipped
    assigned_agent: str | None = None
    compute_tier: str | None = None
    action_id: str | None = None
    action_args: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "stage_type": self.stage_type.value if isinstance(self.stage_type, AutonomousStageType) else str(self.stage_type),
            "title": self.title,
            "status": self.status,
            "assigned_agent": self.assigned_agent,
            "compute_tier": self.compute_tier,
            "action_id": self.action_id,
            "action_args": self.action_args,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutonomousStage:
        return cls(
            id=data.get("id", f"stg-{uuid.uuid4().hex[:8]}"),
            stage_type=AutonomousStageType.from_str(data.get("stage_type", "understand")),
            title=data.get("title", "Stage"),
            status=data.get("status", "pending"),
            assigned_agent=data.get("assigned_agent"),
            compute_tier=data.get("compute_tier"),
            action_id=data.get("action_id"),
            action_args=data.get("action_args") or {},
            result=data.get("result") or {},
            error=data.get("error"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
        )


@dataclass(slots=True)
class AutonomousGoal:
    """Represents an end-to-end autonomous mission triggered by 'Aether, take care of it'."""
    id: str
    workspace_id: str
    goal: str
    raw_prompt: str
    status: AutonomousGoalStatus = AutonomousGoalStatus.PLANNING
    stages: list[AutonomousStage] = field(default_factory=list)
    active_stage_index: int = 0
    allocated_node_id: str | None = None
    allocated_tier: str | None = None
    deliverables: list[dict[str, Any]] = field(default_factory=list)
    approval_execution_id: str | None = None
    learning_summary: str | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "goal": self.goal,
            "raw_prompt": self.raw_prompt,
            "status": self.status.value if isinstance(self.status, AutonomousGoalStatus) else str(self.status),
            "stages": [s.to_dict() for s in self.stages],
            "active_stage_index": self.active_stage_index,
            "allocated_node_id": self.allocated_node_id,
            "allocated_tier": self.allocated_tier,
            "deliverables": self.deliverables,
            "approval_execution_id": self.approval_execution_id,
            "learning_summary": self.learning_summary,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutonomousGoal:
        raw_stages = data.get("stages") or []
        stages = [AutonomousStage.from_dict(s) if isinstance(s, dict) else s for s in raw_stages]
        return cls(
            id=data["id"],
            workspace_id=data.get("workspace_id", "default"),
            goal=data.get("goal", ""),
            raw_prompt=data.get("raw_prompt", ""),
            status=AutonomousGoalStatus.from_str(data.get("status", "planning")),
            stages=stages,
            active_stage_index=int(data.get("active_stage_index", 0)),
            allocated_node_id=data.get("allocated_node_id"),
            allocated_tier=data.get("allocated_tier"),
            deliverables=data.get("deliverables") or [],
            approval_execution_id=data.get("approval_execution_id"),
            learning_summary=data.get("learning_summary"),
            error=data.get("error"),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            completed_at=data.get("completed_at"),
        )
