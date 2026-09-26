"""
Multi-Channel Dispatcher Engine for Aether Notification Fabric (Phase D).
Coordinates non-blocking real-world delivery across Desktop, Telegram, Webhook, Email, and In-App channels.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
import shutil
import smtplib
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.request
import uuid

from aether.notifications.models import (
    ChannelType,
    DeliveryReceipt,
    DeliveryStatus,
    Notification,
    NotificationChannel,
    NotificationPriority,
    NotificationRule,
    NotificationType,
)
from aether.notifications.store import NotificationStore

logger = logging.getLogger(__name__)

PRIORITY_RANKS: dict[str, int] = {
    NotificationPriority.LOW.value: 1,
    NotificationPriority.NORMAL.value: 2,
    NotificationPriority.HIGH.value: 3,
}


def is_in_quiet_hours(start_str: str, end_str: str, current_dt: datetime | None = None) -> bool:
    """Checks whether the given time falls within the quiet hours window [start, end]."""
    try:
        now = (current_dt or datetime.now()).time()
        start_parts = [int(p) for p in start_str.strip().split(":")]
        end_parts = [int(p) for p in end_str.strip().split(":")]
        start_time = datetime.min.time().replace(hour=start_parts[0], minute=start_parts[1])
        end_time = datetime.min.time().replace(hour=end_parts[0], minute=end_parts[1])

        if start_time <= end_time:
            return start_time <= now <= end_time
        # Overnight quiet window (e.g., 22:00 to 08:00)
        return now >= start_time or now <= end_time
    except Exception as exc:
        logger.debug("Failed to calculate quiet hours: %s", exc)
        return False


class NotificationDispatcher:
    """Dispatches notifications across configured and active channels."""

    def __init__(
        self,
        store: NotificationStore,
        connection_service: Any = None,
        event_hub: Any = None,
    ) -> None:
        self.store = store
        self.connection_service = connection_service
        self.event_hub = event_hub

    def dispatch(
        self,
        notification: Notification,
        target_channel_types: list[ChannelType | str] | None = None,
    ) -> list[DeliveryReceipt]:
        """
        Dispatches a notification across applicable channels and records receipts.
        """
        workspace_id = notification.workspace_id
        channels = self.store.ensure_default_channels(workspace_id)
        rules = self.store.ensure_default_rules(workspace_id)

        channel_map = {c.channel_type: c for c in channels}

        # Determine target channels
        if target_channel_types is not None:
            resolved_types = {
                (t if isinstance(t, ChannelType) else ChannelType.from_str(str(t)))
                for t in target_channel_types
            }
        else:
            resolved_types = self._evaluate_rules(notification, rules)

        receipts: list[DeliveryReceipt] = []

        for c_type in resolved_types:
            channel = channel_map.get(c_type)
            if not channel:
                channel = NotificationChannel(
                    id=f"chan-{uuid.uuid4().hex[:8]}",
                    workspace_id=workspace_id,
                    channel_type=c_type,
                    name=c_type.value.capitalize(),
                    enabled=True,
                )
                self.store.save_channel(channel)
                channel_map[c_type] = channel

            if not channel.enabled:
                receipt = DeliveryReceipt(
                    id=f"rcpt-{uuid.uuid4().hex[:10]}",
                    notification_id=notification.id,
                    workspace_id=workspace_id,
                    channel_type=c_type,
                    status=DeliveryStatus.SKIPPED,
                    detail=f"Channel {c_type.value} is disabled",
                    latency_ms=0.0,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                self.store.save_receipt(receipt)
                receipts.append(receipt)
                continue

            # Execute delivery
            start_t = time.perf_counter()
            status, detail = self._deliver_to_channel(channel, notification)
            latency = (time.perf_counter() - start_t) * 1000.0

            receipt = DeliveryReceipt(
                id=f"rcpt-{uuid.uuid4().hex[:10]}",
                notification_id=notification.id,
                workspace_id=workspace_id,
                channel_type=c_type,
                status=status,
                detail=detail,
                latency_ms=latency,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            self.store.save_receipt(receipt)
            receipts.append(receipt)

            # Publish delivery event
            if self.event_hub:
                try:
                    self.event_hub.publish(
                        workspace_id=workspace_id,
                        event_type="notification_delivery",
                        data=receipt.to_dict(),
                    )
                except Exception:
                    pass

        return receipts

    def test_channel(
        self,
        workspace_id: str,
        channel_type: ChannelType | str,
    ) -> DeliveryReceipt:
        """Sends a live test notification through a specific channel."""
        c_type = (
            channel_type
            if isinstance(channel_type, ChannelType)
            else ChannelType.from_str(str(channel_type))
        )
        channel = self.store.get_channel(workspace_id, c_type)
        if not channel:
            channel = NotificationChannel(
                id=f"chan-{uuid.uuid4().hex[:8]}",
                workspace_id=workspace_id,
                channel_type=c_type,
                name=f"{c_type.value.capitalize()} Test",
                enabled=True,
            )
            self.store.save_channel(channel)

        test_notif = Notification(
            id=f"test-{uuid.uuid4().hex[:8]}",
            workspace_id=workspace_id,
            type=ChannelType.IN_APP.value,  # type string
            title="Aether Fabric Channel Verification",
            message=f"Live test dispatch for {c_type.value.upper()} channel completed successfully.",
            priority=NotificationPriority.NORMAL,
        )

        start_t = time.perf_counter()
        if c_type == ChannelType.DESKTOP and self.event_hub:
            try:
                self.event_hub.publish(
                    workspace_id=workspace_id,
                    event_type="notification",
                    data=test_notif.to_dict(),
                )
            except Exception:
                pass
        status, detail = self._deliver_to_channel(channel, test_notif, is_test=True)
        latency = (time.perf_counter() - start_t) * 1000.0

        receipt = DeliveryReceipt(
            id=f"rcpt-{uuid.uuid4().hex[:10]}",
            notification_id=test_notif.id,
            workspace_id=workspace_id,
            channel_type=c_type,
            status=status,
            detail=detail,
            latency_ms=latency,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.store.save_receipt(receipt)
        return receipt

    def _evaluate_rules(
        self,
        notification: Notification,
        rules: list[NotificationRule],
    ) -> set[ChannelType]:
        """Evaluates routing rules against notification attributes and quiet hours."""
        matched_channels: set[ChannelType] = set()
        notif_rank = PRIORITY_RANKS.get(
            notification.priority.value
            if isinstance(notification.priority, NotificationPriority)
            else str(notification.priority),
            2,
        )
        notif_type = (
            notification.type.value
            if isinstance(notification.type, NotificationType)
            else str(notification.type)
        )

        active_rules = [r for r in rules if r.enabled]
        if not active_rules:
            return {ChannelType.IN_APP, ChannelType.DESKTOP}

        for rule in active_rules:
            # Check event type matching
            type_match = ("*" in rule.event_types) or (notif_type in rule.event_types)
            if not type_match:
                continue

            # Check priority threshold
            rule_min_rank = PRIORITY_RANKS.get(
                rule.min_priority.value
                if isinstance(rule.min_priority, NotificationPriority)
                else str(rule.min_priority),
                2,
            )
            if notif_rank < rule_min_rank:
                continue

            # Check quiet hours (unless high priority)
            if rule.quiet_hours_enabled and notif_rank < 3:
                if is_in_quiet_hours(rule.quiet_hours_start, rule.quiet_hours_end):
                    logger.debug("Quiet hours in effect for rule %s; filtering non-urgent", rule.name)
                    # When quiet hours are active, retain only IN_APP
                    matched_channels.add(ChannelType.IN_APP)
                    continue

            for ch in rule.channels:
                matched_channels.add(ch)

        if not matched_channels:
            matched_channels.add(ChannelType.IN_APP)

        return matched_channels

    def _deliver_to_channel(
        self,
        channel: NotificationChannel,
        notification: Notification,
        is_test: bool = False,
    ) -> tuple[DeliveryStatus, str]:
        """Route to individual channel deliverers with error boundaries."""
        ctype = channel.channel_type
        try:
            if ctype == ChannelType.IN_APP:
                return DeliveryStatus.SENT, "Persisted in Notification Center"
            elif ctype == ChannelType.DESKTOP:
                return self._deliver_desktop(channel, notification)
            elif ctype == ChannelType.TELEGRAM:
                return self._deliver_telegram(channel, notification)
            elif ctype == ChannelType.WEBHOOK:
                return self._deliver_webhook(channel, notification)
            elif ctype == ChannelType.EMAIL:
                return self._deliver_email(channel, notification)
            else:
                return DeliveryStatus.SKIPPED, f"Unsupported channel: {ctype}"
        except Exception as exc:
            logger.exception("Delivery failure on channel %s: %s", ctype.value, exc)
            return DeliveryStatus.FAILED, f"Delivery error: {exc}"

    def _deliver_desktop(
        self,
        channel: NotificationChannel,
        notification: Notification,
    ) -> tuple[DeliveryStatus, str]:
        """Sends native OS desktop notification or dispatches to desktop client."""
        title = (notification.title or "Aether").strip()
        message = (notification.message or "").strip()
        sound_enabled = channel.config.get("sound_enabled", True)
        sound_name = channel.config.get("sound", "Glass") if sound_enabled else None

        # 1. When running with Event Hub (Aether Desktop app runtime or SSE server),
        # notification is dispatched to desktop subscribers for native presentation by the desktop owner.
        if self.event_hub is not None:
            sub_count = 0
            if hasattr(self.event_hub, "subscriber_count"):
                sub_count = self.event_hub.subscriber_count(notification.workspace_id)
            elif hasattr(self.event_hub, "_subscribers"):
                sub_count = len(getattr(self.event_hub, "_subscribers", {}).get(notification.workspace_id, []))

            if sub_count > 0:
                return DeliveryStatus.DISPATCHED, f"Dispatched to {sub_count} active desktop subscriber(s) via Event Hub"
            return DeliveryStatus.QUEUED, "Queued in Event Hub; no active desktop subscribers connected"

        # 2. Strict packaged/desktop runtime guard: NEVER execute osascript in packaged desktop app!
        is_desktop_runtime = os.getenv("AETHER_DESKTOP_RUNTIME") == "1" or os.getenv("AETHER_APP_BUNDLE") == "1"
        if is_desktop_runtime:
            return DeliveryStatus.SKIPPED, "Desktop notifications managed directly by Tauri runtime; osascript disabled in packaged mode"

        # 3. macOS development/headless fallback (when event_hub is None and not desktop runtime)
        if sys.platform == "darwin":
            if os.getenv("AETHER_DISABLE_DEV_OSASCRIPT") == "1":
                return DeliveryStatus.SKIPPED, "AppleScript fallback disabled via environment"

            # Sanitize quotes for AppleScript
            clean_title = title.replace("\\", "\\\\").replace('"', '\\"').replace("'", "’")
            clean_msg = message.replace("\\", "\\\\").replace('"', '\\"').replace("'", "’")
            script = f'tell application "System Events" to display notification "{clean_msg}" with title "{clean_title}" subtitle "Aether Notification Fabric"'
            if sound_name:
                script += f' sound name "{sound_name}"'

            try:
                proc = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if proc.returncode == 0:
                    return DeliveryStatus.SENT, "Desktop banner displayed via System Events"
                return DeliveryStatus.FAILED, f"osascript returned {proc.returncode}: {proc.stderr.strip()}"
            except Exception as e:
                return DeliveryStatus.FAILED, f"macOS notification failed: {e}"

        elif sys.platform.startswith("linux"):
            notify_send = shutil.which("notify-send")
            if notify_send:
                try:
                    subprocess.run([notify_send, title, message], timeout=5, check=False)
                    return DeliveryStatus.SENT, "Desktop banner displayed via notify-send"
                except Exception as e:
                    return DeliveryStatus.FAILED, f"notify-send failed: {e}"
            return DeliveryStatus.SKIPPED, "notify-send utility not installed on Linux"

        elif sys.platform == "win32":
            return DeliveryStatus.QUEUED, "Windows notification queued"

        return DeliveryStatus.SKIPPED, f"Desktop notifications not supported on platform {sys.platform}"

    def _deliver_telegram(
        self,
        channel: NotificationChannel,
        notification: Notification,
    ) -> tuple[DeliveryStatus, str]:
        """Delivers notification to Telegram bot or connection bridge."""
        # 1. Connection service connector if active
        if self.connection_service:
            try:
                conn = self.connection_service.get_connection(channel.workspace_id, "telegram")
                if conn and (getattr(conn, "is_verified", False) or getattr(conn, "is_configured", False)):
                    telegram_connector = self.connection_service.get_telegram_connector(channel.workspace_id)
                    chat_id = telegram_connector._get_default_chat_id()
                    if chat_id:
                        if notification.action_required and notification.action_payload:
                            telegram_connector.send_approval_request(
                                chat_id=chat_id,
                                action_id=notification.action_payload.get("action_id", "action"),
                                execution_id=notification.action_payload.get("execution_id", ""),
                                title=notification.title,
                                description=notification.message,
                            )
                            return DeliveryStatus.SENT, f"Interactive Telegram approval sent to chat {chat_id}"
                        else:
                            telegram_connector.send_message(
                                chat_id=chat_id,
                                text=f"🔔 *{notification.title}*\n\n{notification.message}",
                                parse_mode="Markdown",
                            )
                            return DeliveryStatus.SENT, f"Telegram message sent to chat {chat_id}"
            except Exception as e:
                logger.debug("Telegram connection connector delivery failed, checking direct bot config: %s", e)

        # 2. Direct channel bot token & chat_id configuration
        bot_token = channel.config.get("bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = channel.config.get("chat_id") or os.environ.get("TELEGRAM_CHAT_ID")
        if not bot_token or not chat_id:
            return DeliveryStatus.SKIPPED, "Telegram bot_token or chat_id not configured"

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": chat_id,
            "text": f"🔔 *{notification.title}*\n\n{notification.message}",
            "parse_mode": "Markdown",
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                if 200 <= resp.status < 300:
                    return DeliveryStatus.SENT, f"Direct Telegram API delivered to chat {chat_id}"
                return DeliveryStatus.FAILED, f"Telegram API returned status {resp.status}"
        except urllib.error.HTTPError as he:
            return DeliveryStatus.FAILED, f"Telegram HTTP {he.code}: {he.reason}"
        except Exception as e:
            return DeliveryStatus.FAILED, f"Telegram network error: {e}"

    def _deliver_webhook(
        self,
        channel: NotificationChannel,
        notification: Notification,
    ) -> tuple[DeliveryStatus, str]:
        """Delivers notification payload to configured webhook URL."""
        webhook_url = channel.config.get("url") or channel.config.get("webhook_url")
        if not webhook_url:
            return DeliveryStatus.SKIPPED, "Webhook endpoint URL not configured"

        fmt = channel.config.get("format", "generic").lower().strip()
        secret = channel.config.get("secret")

        if fmt in ("slack", "discord"):
            body = {
                "text": f"*{notification.title}*\n{notification.message}",
                "content": f"**{notification.title}**\n{notification.message}",
                "channel_type": notification.type.value if hasattr(notification.type, "value") else str(notification.type),
            }
        else:
            body = {
                "event": "aether.notification",
                "notification": notification.to_dict(),
                "delivered_at": datetime.now(timezone.utc).isoformat(),
            }

        payload = json.dumps(body).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Aether-Notification-Fabric/1.0",
        }
        if secret:
            headers["X-Aether-Signature"] = str(secret)

        req = urllib.request.Request(webhook_url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    return DeliveryStatus.SENT, f"Webhook delivered (HTTP {resp.status})"
                return DeliveryStatus.FAILED, f"Webhook returned HTTP {resp.status}"
        except urllib.error.HTTPError as he:
            return DeliveryStatus.FAILED, f"Webhook HTTP error {he.code}: {he.reason}"
        except Exception as e:
            return DeliveryStatus.FAILED, f"Webhook connection error: {e}"

    def _deliver_email(
        self,
        channel: NotificationChannel,
        notification: Notification,
    ) -> tuple[DeliveryStatus, str]:
        """Delivers notification via SMTP relay."""
        smtp_host = channel.config.get("smtp_host")
        to_addrs = channel.config.get("to_addrs") or []
        if isinstance(to_addrs, str):
            to_addrs = [a.strip() for a in to_addrs.split(",") if a.strip()]

        if not smtp_host or not to_addrs:
            return DeliveryStatus.SKIPPED, "SMTP host or recipients not configured"

        smtp_port = int(channel.config.get("smtp_port") or 587)
        smtp_user = channel.config.get("smtp_user")
        smtp_pass = channel.config.get("smtp_pass")
        from_addr = channel.config.get("from_addr") or smtp_user or "notifications@aether.local"

        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart()
        msg["From"] = from_addr
        msg["To"] = ", ".join(to_addrs)
        msg["Subject"] = f"[Aether] {notification.title}"
        body_text = f"{notification.title}\n\n{notification.message}\n\nPriority: {notification.priority}\nTime: {notification.created_at}"
        msg.attach(MIMEText(body_text, "plain"))

        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.ehlo()
                if server.has_extn("STARTTLS"):
                    server.starttls()
                    server.ehlo()
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(from_addr, to_addrs, msg.as_string())
            return DeliveryStatus.SENT, f"Email delivered to {len(to_addrs)} recipients"
        except Exception as e:
            return DeliveryStatus.FAILED, f"SMTP relay failed: {e}"
