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


class ChannelType(StrEnum):
    IN_APP = "in_app"
    DESKTOP = "desktop"
    TELEGRAM = "telegram"
    WEBHOOK = "webhook"
    EMAIL = "email"

    @classmethod
    def from_str(cls, val: str) -> ChannelType:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.IN_APP


class DeliveryStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
    PENDING = "pending"

    @classmethod
    def from_str(cls, val: str) -> DeliveryStatus:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.FAILED


@dataclass(slots=True)
class NotificationChannel:
    """Configuration for a delivery channel in the Notification Fabric."""
    id: str
    workspace_id: str
    channel_type: ChannelType
    name: str
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "channel_type": self.channel_type.value if isinstance(self.channel_type, ChannelType) else str(self.channel_type),
            "name": self.name,
            "enabled": self.enabled,
            "config": self.config,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NotificationChannel:
        return cls(
            id=data.get("id") or f"chan-{uuid.uuid4().hex[:8]}",
            workspace_id=data.get("workspace_id", "default"),
            channel_type=ChannelType.from_str(data.get("channel_type", "in_app")),
            name=data.get("name", ""),
            enabled=bool(data.get("enabled", True)),
            config=dict(data.get("config") or {}),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(slots=True)
class NotificationRule:
    """Routing and filtering rule for notifications."""
    id: str
    workspace_id: str
    name: str
    enabled: bool = True
    event_types: list[str] = field(default_factory=lambda: ["*"])
    min_priority: NotificationPriority = NotificationPriority.NORMAL
    channels: list[ChannelType] = field(default_factory=lambda: [ChannelType.IN_APP, ChannelType.DESKTOP])
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "08:00"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "name": self.name,
            "enabled": self.enabled,
            "event_types": self.event_types,
            "min_priority": self.min_priority.value if isinstance(self.min_priority, NotificationPriority) else str(self.min_priority),
            "channels": [c.value if isinstance(c, ChannelType) else str(c) for c in self.channels],
            "quiet_hours_enabled": self.quiet_hours_enabled,
            "quiet_hours_start": self.quiet_hours_start,
            "quiet_hours_end": self.quiet_hours_end,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NotificationRule:
        raw_channels = data.get("channels") or ["in_app", "desktop"]
        channels = [ChannelType.from_str(c) for c in raw_channels]
        return cls(
            id=data.get("id") or f"rule-{uuid.uuid4().hex[:8]}",
            workspace_id=data.get("workspace_id", "default"),
            name=data.get("name", "Default Rule"),
            enabled=bool(data.get("enabled", True)),
            event_types=list(data.get("event_types") or ["*"]),
            min_priority=NotificationPriority.from_str(data.get("min_priority", "normal")),
            channels=channels,
            quiet_hours_enabled=bool(data.get("quiet_hours_enabled", False)),
            quiet_hours_start=data.get("quiet_hours_start", "22:00"),
            quiet_hours_end=data.get("quiet_hours_end", "08:00"),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(slots=True)
class DeliveryReceipt:
    """Audit log of a delivery attempt to a specific channel."""
    id: str
    notification_id: str
    workspace_id: str
    channel_type: ChannelType
    status: DeliveryStatus
    detail: str = ""
    latency_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "notification_id": self.notification_id,
            "workspace_id": self.workspace_id,
            "channel_type": self.channel_type.value if isinstance(self.channel_type, ChannelType) else str(self.channel_type),
            "status": self.status.value if isinstance(self.status, DeliveryStatus) else str(self.status),
            "detail": self.detail,
            "latency_ms": round(self.latency_ms, 2),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeliveryReceipt:
        return cls(
            id=data.get("id") or f"rcpt-{uuid.uuid4().hex[:10]}",
            notification_id=data.get("notification_id", ""),
            workspace_id=data.get("workspace_id", "default"),
            channel_type=ChannelType.from_str(data.get("channel_type", "in_app")),
            status=DeliveryStatus.from_str(data.get("status", "sent")),
            detail=data.get("detail", ""),
            latency_ms=float(data.get("latency_ms", 0.0)),
            timestamp=data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(slots=True)
class NotificationBriefing:
    """Rich executive briefing summarizing task/mission completion or proactive insights."""
    id: str
    workspace_id: str
    title: str
    summary: str
    highlights: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    action_links: list[dict[str, str]] = field(default_factory=list)
    channels_dispatched: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "title": self.title,
            "summary": self.summary,
            "highlights": self.highlights,
            "metrics": self.metrics,
            "action_links": self.action_links,
            "channels_dispatched": self.channels_dispatched,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NotificationBriefing:
        return cls(
            id=data.get("id") or f"brf-{uuid.uuid4().hex[:8]}",
            workspace_id=data.get("workspace_id", "default"),
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            highlights=list(data.get("highlights") or []),
            metrics=dict(data.get("metrics") or {}),
            action_links=list(data.get("action_links") or []),
            channels_dispatched=list(data.get("channels_dispatched") or []),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )

