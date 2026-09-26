"""
Domain models for Aether Activity Feed (Phase C).
Provides human-readable, outcome-focused activity records.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid


class ActivityCategory(StrEnum):
    WORK = "work"
    ACTION = "action"
    WORKFORCE = "workforce"
    CONNECTION = "connection"
    SYSTEM = "system"

    @classmethod
    def from_str(cls, val: str) -> ActivityCategory:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.WORK


class ActivityStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

    # Backward compatibility aliases
    PENDING_APPROVAL = "waiting_approval"
    SUCCEEDED = "completed"

    @classmethod
    def from_str(cls, val: str) -> ActivityStatus:
        if isinstance(val, cls):
            return val
        clean = str(val).lower().strip()
        aliases = {
            "pending_approval": cls.WAITING_APPROVAL,
            "waiting_approval": cls.WAITING_APPROVAL,
            "in_progress": cls.IN_PROGRESS,
            "running": cls.IN_PROGRESS,
            "queued": cls.IN_PROGRESS,
            "completed": cls.COMPLETED,
            "succeeded": cls.COMPLETED,
            "success": cls.COMPLETED,
            "failed": cls.FAILED,
            "rejected": cls.REJECTED,
            "cancelled": cls.CANCELLED,
            "canceled": cls.CANCELLED,
        }
        if clean in aliases:
            return aliases[clean]
        return cls.IN_PROGRESS

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            norm = other.lower().strip()
            if self.value == "waiting_approval" and norm in ("waiting_approval", "pending_approval"):
                return True
            if self.value == "completed" and norm in ("completed", "succeeded", "success"):
                return True
            return self.value == norm
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash(self.value)


@dataclass(slots=True)
class ActivityEvent:
    id: str
    workspace_id: str
    title: str
    description: str
    category: ActivityCategory = ActivityCategory.WORK
    status: ActivityStatus = ActivityStatus.COMPLETED
    link_view: str | None = None
    link_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "title": self.title,
            "description": self.description,
            "category": self.category.value if isinstance(self.category, ActivityCategory) else str(self.category),
            "status": self.status.value if isinstance(self.status, ActivityStatus) else str(self.status),
            "link_view": self.link_view,
            "link_id": self.link_id,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActivityEvent:
        return cls(
            id=data.get("id") or f"act-{uuid.uuid4().hex[:12]}",
            workspace_id=data.get("workspace_id", "default"),
            title=data.get("title", ""),
            description=data.get("description", ""),
            category=ActivityCategory.from_str(data.get("category", "work")),
            status=ActivityStatus.from_str(data.get("status", "completed")),
            link_view=data.get("link_view"),
            link_id=data.get("link_id"),
            metadata=dict(data.get("metadata") or {}),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )
