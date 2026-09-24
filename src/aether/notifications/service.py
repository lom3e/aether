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
        action_payload: dict[str, Any] | None = None,
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

        meta = dict(metadata or {})
        if action_payload:
            meta["action_payload"] = action_payload

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
            metadata=meta,
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

    def notify_approval(
        self,
        workspace_id: str,
        title: str,
        message: str,
        action_id: str,
        execution_id: str,
        prompt: str,
        risk_tier: str = "medium",
        link_view: str = "activity",
        link_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Notification:
        """Convenience method to dispatch a safety approval notification with structured action payload."""
        action_payload = {
            "action_id": action_id,
            "execution_id": execution_id,
            "prompt": prompt,
            "risk_tier": risk_tier,
        }
        return self.notify(
            workspace_id=workspace_id,
            type=NotificationType.APPROVAL_REQUIRED,
            title=title,
            message=message,
            priority=NotificationPriority.HIGH,
            link_view=link_view,
            link_id=link_id or execution_id,
            action_required=True,
            action_payload=action_payload,
            metadata=metadata,
        )

    def get_summary(self, workspace_id: str) -> dict[str, Any]:
        """Returns aggregated notification summary including unread and pending approvals."""
        all_notifs = self.store.list(workspace_id=workspace_id, limit=200)
        unread = [n for n in all_notifs if n.status == NotificationStatus.UNREAD]
        pending_approvals = [n for n in unread if n.action_required]
        high_priority = [n for n in unread if n.priority == NotificationPriority.HIGH]
        return {
            "workspace_id": workspace_id,
            "total_count": len(all_notifs),
            "unread_count": len(unread),
            "pending_approvals_count": len(pending_approvals),
            "high_priority_count": len(high_priority),
        }

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
