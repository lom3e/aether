"""
Service layer for Aether Universal Notification Fabric (Phase D).
Coordinates real-world multi-channel notifications, approvals, task completions, and event delivery.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from aether.notifications.dispatcher import NotificationDispatcher
from aether.notifications.models import (
    ChannelType,
    DeliveryReceipt,
    DeliveryStatus,
    Notification,
    NotificationBriefing,
    NotificationChannel,
    NotificationPriority,
    NotificationRule,
    NotificationStatus,
    NotificationType,
)
from aether.notifications.store import NotificationStore

logger = logging.getLogger(__name__)


class NotificationService:
    """Service managing notifications, multi-channel dispatch, and briefings across Aether."""

    def __init__(
        self,
        store: NotificationStore,
        activity_service: Any = None,
        event_hub: Any = None,
        connection_service: Any = None,
        dispatcher: NotificationDispatcher | None = None,
    ) -> None:
        self.store = store
        self.activity_service = activity_service
        self.event_hub = event_hub
        self.connection_service = connection_service
        self.dispatcher = dispatcher or NotificationDispatcher(
            store=self.store,
            connection_service=self.connection_service,
            event_hub=self.event_hub,
        )

    def notify(
        self,
        workspace_id: str,
        type: NotificationType | str,
        title: str,
        message: str = "",
        priority: NotificationPriority | str = NotificationPriority.NORMAL,
        link_view: str | None = None,
        link_id: str | None = None,
        action_required: bool = False,
        action_payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        target_channels: list[ChannelType | str] | None = None,
        target_type: str | Any | None = None,
        target_id: str | None = None,
        deep_link: str | None = None,
        primary_action: dict[str, Any] | str | None = None,
        secondary_action: dict[str, Any] | str | None = None,
        open_target: dict[str, Any] | None = None,
        approve_action: dict[str, Any] | None = None,
        reject_action: dict[str, Any] | None = None,
        body: str | None = None,
        severity: NotificationPriority | str | None = None,
        requires_action: bool | None = None,
        notification_id: str | None = None,
    ) -> Notification:
        """Emits, persists, and dispatches a multi-channel notification."""
        notif_type = (
            type if isinstance(type, NotificationType) else NotificationType.from_str(str(type))
        )
        resolved_prio = severity if severity is not None else priority
        notif_priority = (
            resolved_prio
            if isinstance(resolved_prio, NotificationPriority)
            else NotificationPriority.from_str(str(resolved_prio))
        )
        msg = body if (body is not None and not message) else message
        act_req = requires_action if requires_action is not None else action_required
        nid = notification_id or f"notif-{uuid.uuid4().hex[:12]}"

        meta = dict(metadata or {})
        if action_payload:
            meta["action_payload"] = action_payload

        notification = Notification(
            id=nid,
            workspace_id=workspace_id,
            type=notif_type,
            title=title,
            message=msg,
            priority=notif_priority,
            status=NotificationStatus.UNREAD,
            link_view=link_view,
            link_id=link_id,
            action_required=act_req,
            target_type=target_type,
            target_id=target_id,
            deep_link=deep_link,
            primary_action=primary_action,
            secondary_action=secondary_action,
            open_target=open_target,
            approve_action=approve_action,
            reject_action=reject_action,
            metadata=meta,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        saved = self.store.save(notification)

        # Forward critical alerts or approvals to Telegram if connector is active
        if self.connection_service:
            try:
                conn = self.connection_service.get_connection(workspace_id, "telegram")
                if conn and (getattr(conn, "is_verified", False) or getattr(conn, "is_configured", False)):
                    telegram_connector = self.connection_service.get_telegram_connector(workspace_id)
                    chat_id = telegram_connector._get_default_chat_id()
                    if chat_id:
                        if action_required and action_payload and "execution_id" in action_payload:
                            telegram_connector.send_approval_request(
                                chat_id=chat_id,
                                action_id=action_payload.get("action_id", "action"),
                                execution_id=action_payload.get("execution_id", ""),
                                title=title,
                                description=message,
                            )
                        elif notif_priority == NotificationPriority.HIGH:
                            telegram_connector.send_message(
                                chat_id=chat_id,
                                text=f"🚨 *{title}*\n\n{message}",
                                parse_mode="Markdown",
                            )
            except Exception as e:
                logger.debug("Could not forward notification to Telegram connector: %s", e)

        # Dispatch across multi-channel fabric
        try:
            receipts = self.dispatcher.dispatch(saved, target_channel_types=target_channels)
            meta["delivery_count"] = len(receipts)
        except Exception as exc:
            logger.warning("Dispatcher error during notify: %s", exc)


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
        target_type: str | NotificationTargetType | None = None,
        target_id: str | None = None,
        deep_link: str | None = None,
        primary_action: dict[str, Any] | str | None = None,
        secondary_action: dict[str, Any] | str | None = None,
        **kwargs: Any,
    ) -> Notification:
        """Convenience method to dispatch a safety approval notification with structured action payload."""
        action_payload = {
            "action_id": action_id,
            "execution_id": execution_id,
            "prompt": prompt,
            "risk_tier": risk_tier,
        }
        p_act = primary_action or {"label": "Approve", "action": "approve", "target_id": execution_id}
        s_act = secondary_action or {"label": "Reject", "action": "reject", "target_id": execution_id}
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
            target_type=target_type or "approval",
            target_id=target_id or execution_id,
            deep_link=deep_link,
            primary_action=p_act,
            secondary_action=s_act,
            metadata=metadata,
            **kwargs,
        )

    def dispatch_briefing(
        self,
        workspace_id: str,
        title: str,
        summary: str,
        highlights: list[str] | None = None,
        metrics: dict[str, Any] | None = None,
        action_links: list[dict[str, str]] | None = None,
        channels: list[ChannelType | str] | None = None,
    ) -> NotificationBriefing:
        """
        Creates and dispatches an executive notification briefing across specified or default channels.
        """
        resolved_highlights = list(highlights or [])
        resolved_metrics = dict(metrics or {})
        resolved_actions = list(action_links or [])

        # Format briefing text
        details = [f"📊 Executive Summary: {summary}"]
        if resolved_highlights:
            details.append("Highlights:\n" + "\n".join(f"• {h}" for h in resolved_highlights))
        if resolved_metrics:
            details.append("Key Metrics: " + ", ".join(f"{k}: {v}" for k, v in resolved_metrics.items()))

        formatted_msg = "\n\n".join(details)

        # Emit in-app notification and trigger multi-channel dispatch
        notif = self.notify(
            workspace_id=workspace_id,
            type=NotificationType.INSIGHT,
            title=f"📋 Briefing: {title}",
            message=formatted_msg,
            priority=NotificationPriority.NORMAL,
            metadata={
                "briefing": True,
                "metrics": resolved_metrics,
                "highlights": resolved_highlights,
                "action_links": resolved_actions,
            },
            target_channels=channels,
        )

        channels_sent: list[str] = []
        if channels:
            channels_sent = [
                c.value if isinstance(c, ChannelType) else str(c)
                for c in channels
            ]
        else:
            recent_receipts = self.store.list_receipts(workspace_id, limit=10)
            channels_sent = [
                r.channel_type.value if hasattr(r.channel_type, "value") else str(r.channel_type)
                for r in recent_receipts if r.notification_id == notif.id and r.status == DeliveryStatus.SENT
            ]

        briefing = NotificationBriefing(
            id=f"brf-{uuid.uuid4().hex[:8]}",
            workspace_id=workspace_id,
            title=title,
            summary=summary,
            highlights=resolved_highlights,
            metrics=resolved_metrics,
            action_links=resolved_actions,
            channels_dispatched=channels_sent,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        saved_briefing = self.store.save_briefing(briefing)

        if self.event_hub:
            try:
                self.event_hub.publish(
                    workspace_id=workspace_id,
                    event_type="notification_briefing",
                    data=saved_briefing.to_dict(),
                )
            except Exception:
                pass

        return saved_briefing

    # -------------------------------------------------------------------------
    # Channel & Rule Management
    # -------------------------------------------------------------------------

    def get_channels(self, workspace_id: str) -> list[NotificationChannel]:
        """Lists configured channels for a workspace."""
        return self.store.ensure_default_channels(workspace_id)

    def configure_channel(
        self,
        workspace_id: str,
        channel_type: ChannelType | str,
        enabled: bool | None = None,
        name: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> NotificationChannel:
        """Enables, disables, or reconfigures a notification delivery channel."""
        ctype = (
            channel_type
            if isinstance(channel_type, ChannelType)
            else ChannelType.from_str(str(channel_type))
        )
        self.store.ensure_default_channels(workspace_id)
        existing = self.store.get_channel(workspace_id, ctype)

        if not existing:
            existing = NotificationChannel(
                id=f"chan-{uuid.uuid4().hex[:8]}",
                workspace_id=workspace_id,
                channel_type=ctype,
                name=name or ctype.value.capitalize(),
                enabled=True if enabled is None else enabled,
                config=config or {},
            )
        else:
            if enabled is not None:
                existing.enabled = enabled
            if name is not None:
                existing.name = name
            if config is not None:
                existing.config.update(config)

        return self.store.save_channel(existing)

    def test_channel(
        self,
        workspace_id: str,
        channel_type: ChannelType | str,
    ) -> DeliveryReceipt:
        """Sends a live test notification through a single channel."""
        return self.dispatcher.test_channel(workspace_id, channel_type)

    def get_rules(self, workspace_id: str) -> list[NotificationRule]:
        """Lists routing rules for a workspace."""
        return self.store.ensure_default_rules(workspace_id)

    def configure_rule(
        self,
        workspace_id: str,
        name: str,
        event_types: list[str] | None = None,
        min_priority: str | None = None,
        channels: list[str] | None = None,
        quiet_hours_enabled: bool | None = None,
        quiet_hours_start: str | None = None,
        quiet_hours_end: str | None = None,
        rule_id: str | None = None,
    ) -> NotificationRule:
        """Creates or updates a notification routing rule."""
        self.store.ensure_default_rules(workspace_id)
        existing = self.store.get_rule(workspace_id, rule_id) if rule_id else None

        if not existing:
            resolved_channels = [ChannelType.from_str(c) for c in (channels or ["in_app", "desktop"])]
            rule = NotificationRule(
                id=rule_id or f"rule-{uuid.uuid4().hex[:8]}",
                workspace_id=workspace_id,
                name=name,
                enabled=True,
                event_types=list(event_types or ["*"]),
                min_priority=NotificationPriority.from_str(min_priority or "normal"),
                channels=resolved_channels,
                quiet_hours_enabled=bool(quiet_hours_enabled) if quiet_hours_enabled is not None else False,
                quiet_hours_start=quiet_hours_start or "22:00",
                quiet_hours_end=quiet_hours_end or "08:00",
            )
        else:
            rule = existing
            rule.name = name
            if event_types is not None:
                rule.event_types = event_types
            if min_priority is not None:
                rule.min_priority = NotificationPriority.from_str(min_priority)
            if channels is not None:
                rule.channels = [ChannelType.from_str(c) for c in channels]
            if quiet_hours_enabled is not None:
                rule.quiet_hours_enabled = quiet_hours_enabled
            if quiet_hours_start is not None:
                rule.quiet_hours_start = quiet_hours_start
            if quiet_hours_end is not None:
                rule.quiet_hours_end = quiet_hours_end

        return self.store.save_rule(rule)

    def delete_rule(self, workspace_id: str, rule_id: str) -> bool:
        """Removes a notification rule."""
        return self.store.delete_rule(workspace_id, rule_id)

    def get_delivery_history(self, workspace_id: str, limit: int = 50) -> list[DeliveryReceipt]:
        """Returns recent channel delivery receipts."""
        return self.store.list_receipts(workspace_id, limit=limit)

    def list_briefings(self, workspace_id: str, limit: int = 20) -> list[NotificationBriefing]:
        """Lists executive briefings."""
        return self.store.list_briefings(workspace_id, limit=limit)

    def get_briefing(self, briefing_id: str) -> NotificationBriefing | None:
        """Retrieves an executive briefing by ID."""
        return self.store.get_briefing(briefing_id)

    # -------------------------------------------------------------------------
    # In-App Notifications API
    # -------------------------------------------------------------------------

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

    def update_delivery_receipt(
        self,
        workspace_id: str,
        notification_id: str,
        channel_type: ChannelType | str,
        status: DeliveryStatus | str,
        detail: str | None = None,
    ) -> DeliveryReceipt | None:
        """Updates delivery receipt state with real feedback from client surfaces."""
        receipt = self.store.update_receipt_status(
            notification_id=notification_id,
            channel_type=channel_type,
            status=status,
            detail=detail,
        )
        if receipt and self.event_hub:
            self.event_hub.publish(
                workspace_id=workspace_id,
                event_type="delivery_receipt_update",
                data=receipt.to_dict(),
            )
        return receipt

    def get_unread_count(self, workspace_id: str) -> int:
        """Returns the number of unread notifications."""
        return self.store.get_unread_count(workspace_id)
