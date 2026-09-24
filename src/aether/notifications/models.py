"""
Domain models for Aether Universal Notification Fabric (Phase D).
Defines notification types, priorities, statuses, and payload models.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid


class NotificationType(StrEnum):
    APPROVAL_REQUIRED = "approval_required"  # Action requires user confirmation (Safety Gate)
    TASK_COMPLETED = "task_completed"        # Background task / Mission finished
    TASK_FAILED = "task_failed"              # Background task / Mission failed
    ACTION_COMPLETED = "action_completed"    # Action executed successfully
    ACTION_FAILED = "action_failed"          # Action execution error
    INSIGHT = "insight"                      # Proactive intelligence / recommendation

    @classmethod
    def from_str(cls, val: str) -> NotificationType:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.INSIGHT


class NotificationPriority(StrEnum):
    HIGH = "high"       # Urgent approvals, destructive action confirmations
    NORMAL = "normal"   # Task completions, action results
    LOW = "low"         # Informational insights, background telemetry summaries

    @classmethod
    def from_str(cls, val: str) -> NotificationPriority:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.NORMAL


class NotificationStatus(StrEnum):
    UNREAD = "unread"
    READ = "read"
    DISMISSED = "dismissed"

    @classmethod
    def from_str(cls, val: str) -> NotificationStatus:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.UNREAD


@dataclass(slots=True)
class Notification:
    """A real-world notification item in Aether."""
    id: str
    workspace_id: str
    type: NotificationType
    title: str
    message: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    status: NotificationStatus = NotificationStatus.UNREAD
    link_view: str | None = None   # Target UI view: 'home', 'work', 'connections', 'activity'
    link_id: str | None = None     # Target entity ID (execution_id, mission_id, task_id)
    action_required: bool = False  # True if waiting for user decision (Approve/Decline)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def action_payload(self) -> dict[str, Any] | None:
        return self.metadata.get("action_payload")

    @action_payload.setter
    def action_payload(self, val: dict[str, Any] | None) -> None:
        if val is None:
            self.metadata.pop("action_payload", None)
        else:
            self.metadata["action_payload"] = val

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "type": self.type.value if isinstance(self.type, NotificationType) else str(self.type),
            "title": self.title,
            "message": self.message,
            "priority": self.priority.value if isinstance(self.priority, NotificationPriority) else str(self.priority),
            "status": self.status.value if isinstance(self.status, NotificationStatus) else str(self.status),
            "link_view": self.link_view,
            "link_id": self.link_id,
            "action_required": self.action_required,
            "action_payload": self.action_payload,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Notification:
        meta = dict(data.get("metadata") or {})
        if "action_payload" in data and data["action_payload"] and "action_payload" not in meta:
            meta["action_payload"] = data["action_payload"]
        return cls(
            id=data.get("id") or f"notif-{uuid.uuid4().hex[:12]}",
            workspace_id=data.get("workspace_id", "default"),
            type=NotificationType.from_str(data.get("type", "insight")),
            title=data.get("title", ""),
            message=data.get("message", ""),
            priority=NotificationPriority.from_str(data.get("priority", "normal")),
            status=NotificationStatus.from_str(data.get("status", "unread")),
            link_view=data.get("link_view"),
            link_id=data.get("link_id"),
            action_required=bool(data.get("action_required", False)),
            metadata=meta,
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )
