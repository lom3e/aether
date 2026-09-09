"""
Service layer for Aether Universal Notification Fabric (Phase D).
Coordinates real-world notifications, approvals, task completions, and event delivery.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from aether.notifications.models import (
    Notification,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from aether.notifications.store import NotificationStore

logger = logging.getLogger(__name__)


class NotificationService:
    """Service managing notifications and alerts across Aether."""

    def __init__(
        self,
        store: NotificationStore,
        activity_service: Any = None,
        event_hub: Any = None,
    ) -> None:
        self.store = store
        self.activity_service = activity_service
        self.event_hub = event_hub

    def notify(
        self,
        workspace_id: str,
        type: NotificationType | str,
        title: str,
        message: str,
        priority: NotificationPriority | str = NotificationPriority.NORMAL,
        link_view: str | None = None,
        link_id: str | None = None,
        action_required: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> Notification:
        """Emits and persists a real notification."""
        notif_type = (
            type if isinstance(type, NotificationType) else NotificationType.from_str(str(type))
        )
        notif_priority = (
            priority
            if isinstance(priority, NotificationPriority)
            else NotificationPriority.from_str(str(priority))
        )

        notification = Notification(
            id=f"notif-{uuid.uuid4().hex[:12]}",
            workspace_id=workspace_id,
            type=notif_type,
            title=title,
            message=message,
            priority=notif_priority,
            status=NotificationStatus.UNREAD,
            link_view=link_view,
            link_id=link_id,
            action_required=action_required,
            metadata=metadata or {},
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        saved = self.store.save(notification)

        # Broadcast via Event Hub if available
        if self.event_hub:
            try:
                self.event_hub.publish(
                    workspace_id=workspace_id,
                    event_type="notification",
                    data=saved.to_dict(),
                )
            except Exception as e:
                logger.debug(f"Could not broadcast notification via event hub: {e}")

        logger.info(f"Notification emitted [{notif_type.value}]: {title} ({workspace_id})")
        return saved

    def list_notifications(
        self,
        workspace_id: str,
        unread_only: bool = False,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Notification]:
        """Lists notifications for a workspace."""
        return self.store.list(
            workspace_id=workspace_id,
            status=status,
            unread_only=unread_only,
            limit=limit,
        )

    def mark_as_read(self, workspace_id: str, notification_id: str) -> bool:
        """Marks a notification as read."""
        success = self.store.mark_as_read(notification_id)
        if success and self.event_hub:
            self.event_hub.publish(
                workspace_id=workspace_id,
                event_type="notification_status",
                data={"id": notification_id, "status": "read"},
            )
        return success

    def mark_all_read(self, workspace_id: str) -> int:
        """Marks all unread notifications in a workspace as read."""
        count = self.store.mark_all_read(workspace_id)
        if count > 0 and self.event_hub:
            self.event_hub.publish(
                workspace_id=workspace_id,
                event_type="notification_status",
                data={"status": "all_read", "count": count},
            )
        return count

    def dismiss(self, workspace_id: str, notification_id: str) -> bool:
        """Dismisses a notification."""
        success = self.store.dismiss(notification_id)
        if success and self.event_hub:
            self.event_hub.publish(
                workspace_id=workspace_id,
                event_type="notification_status",
                data={"id": notification_id, "status": "dismissed"},
            )
        return success

    def get_unread_count(self, workspace_id: str) -> int:
        """Returns the number of unread notifications."""
        return self.store.get_unread_count(workspace_id)
