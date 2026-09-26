"""
SQLite persistence for Aether Universal Notification Fabric (Phase D).
Provides thread-safe WAL storage, indexing, and state management.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
import threading
from typing import Any, Generator
import uuid

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

logger = logging.getLogger(__name__)


class NotificationStore:
    """SQLite-backed persistent store for notifications."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._conns_lock = threading.Lock()
        self._all_conns: set[sqlite3.Connection] = set()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=10.0,
                check_same_thread=False,
                isolation_level=None,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute("PRAGMA foreign_keys = ON;")
            with self._conns_lock:
                self._all_conns.add(conn)
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        conn = self._get_connection()
        conn.execute("BEGIN IMMEDIATE;")
        cursor = conn.cursor()
        try:
            yield cursor
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def _init_db(self) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    link_view TEXT,
                    link_id TEXT,
                    action_required INTEGER NOT NULL DEFAULT 0,
                    target_type TEXT,
                    target_id TEXT,
                    deep_link TEXT,
                    primary_action TEXT,
                    secondary_action TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            for col in ("target_type", "target_id", "deep_link", "primary_action", "secondary_action"):
                try:
                    cursor.execute(f"ALTER TABLE notifications ADD COLUMN {col} TEXT;")
                except sqlite3.OperationalError:
                    pass
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_notif_ws_status ON notifications(workspace_id, status, created_at DESC);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_notif_created ON notifications(created_at DESC);"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_channels (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    channel_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    config TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_channel_ws_type ON notification_channels(workspace_id, channel_type);"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_rules (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    event_types TEXT NOT NULL,
                    min_priority TEXT NOT NULL,
                    channels TEXT NOT NULL,
                    quiet_hours_enabled INTEGER NOT NULL DEFAULT 0,
                    quiet_hours_start TEXT,
                    quiet_hours_end TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_rules_ws ON notification_rules(workspace_id, enabled);"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_receipts (
                    id TEXT PRIMARY KEY,
                    notification_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    channel_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    latency_ms REAL NOT NULL DEFAULT 0.0,
                    timestamp TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_receipts_ws_time ON delivery_receipts(workspace_id, timestamp DESC);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_receipts_notif ON delivery_receipts(notification_id);"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS briefings (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    highlights TEXT NOT NULL,
                    metrics TEXT NOT NULL,
                    action_links TEXT NOT NULL,
                    channels_dispatched TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_briefings_ws ON briefings(workspace_id, created_at DESC);"
            )

    def save(self, notification: Notification) -> Notification:
        """Inserts or updates a notification."""
        t_type = (
            notification.target_type.value
            if hasattr(notification.target_type, "value")
            else (str(notification.target_type) if notification.target_type else None)
        )
        p_act = (
            json.dumps(notification.primary_action)
            if isinstance(notification.primary_action, dict)
            else (str(notification.primary_action) if notification.primary_action else None)
        )
        s_act = (
            json.dumps(notification.secondary_action)
            if isinstance(notification.secondary_action, dict)
            else (str(notification.secondary_action) if notification.secondary_action else None)
        )
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO notifications (
                    id, workspace_id, type, title, message, priority,
                    status, link_view, link_id, action_required,
                    target_type, target_id, deep_link, primary_action, secondary_action,
                    metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    notification.id,
                    notification.workspace_id,
                    notification.type.value if isinstance(notification.type, NotificationType) else str(notification.type),
                    notification.title,
                    notification.message,
                    notification.priority.value if isinstance(notification.priority, NotificationPriority) else str(notification.priority),
                    notification.status.value if isinstance(notification.status, NotificationStatus) else str(notification.status),
                    notification.link_view,
                    notification.link_id,
                    1 if notification.action_required else 0,
                    t_type,
                    notification.target_id,
                    notification.deep_link,
                    p_act,
                    s_act,
                    json.dumps(notification.metadata),
                    notification.created_at,
                ),
            )
        return notification

    def get(self, notification_id: str) -> Notification | None:
        """Retrieves a single notification by ID."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM notifications WHERE id = ?", (notification_id,)).fetchone()
        if not row:
            return None
        return self._row_to_notification(row)

    def list(
        self,
        workspace_id: str,
        status: str | None = None,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        """Lists notifications for a workspace, optionally filtered by status."""
        conn = self._get_connection()
        params: list[Any] = [workspace_id]
        sql = "SELECT * FROM notifications WHERE workspace_id = ?"

        if unread_only:
            sql += " AND status = ?"
            params.append(NotificationStatus.UNREAD.value)
        elif status:
            sql += " AND status = ?"
            params.append(status)
        else:
            sql += " AND status != ?"
            params.append(NotificationStatus.DISMISSED.value)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, limit))

        rows = conn.execute(sql, params).fetchall()
        return [self._row_to_notification(r) for r in rows]

    def mark_as_read(self, notification_id: str) -> bool:
        """Marks a notification as read."""
        with self._transaction() as cursor:
            cursor.execute(
                "UPDATE notifications SET status = ? WHERE id = ?",
                (NotificationStatus.READ.value, notification_id),
            )
            return cursor.rowcount > 0

    def mark_all_read(self, workspace_id: str) -> int:
        """Marks all unread notifications in a workspace as read."""
        with self._transaction() as cursor:
            cursor.execute(
                "UPDATE notifications SET status = ? WHERE workspace_id = ? AND status = ?",
                (NotificationStatus.READ.value, workspace_id, NotificationStatus.UNREAD.value),
            )
            return cursor.rowcount

    def dismiss(self, notification_id: str) -> bool:
        """Dismisses a notification."""
        with self._transaction() as cursor:
            cursor.execute(
                "UPDATE notifications SET status = ? WHERE id = ?",
                (NotificationStatus.DISMISSED.value, notification_id),
            )
            return cursor.rowcount > 0

    def get_unread_count(self, workspace_id: str) -> int:
        """Returns the number of unread notifications for a workspace."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM notifications WHERE workspace_id = ? AND status = ?",
            (workspace_id, NotificationStatus.UNREAD.value),
        ).fetchone()
        return int(row["cnt"]) if row else 0

    # -------------------------------------------------------------------------
    # Channel Management
    # -------------------------------------------------------------------------

    def ensure_default_channels(self, workspace_id: str) -> list[NotificationChannel]:
        """Ensures default delivery channels exist for the workspace."""
        existing = self.list_channels(workspace_id)
        if existing:
            return existing
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        defaults = [
            NotificationChannel(
                id=f"chan-{uuid.uuid4().hex[:8]}",
                workspace_id=workspace_id,
                channel_type=ChannelType.IN_APP,
                name="In-App Notification Center",
                enabled=True,
                config={},
                created_at=now,
                updated_at=now,
            ),
            NotificationChannel(
                id=f"chan-{uuid.uuid4().hex[:8]}",
                workspace_id=workspace_id,
                channel_type=ChannelType.DESKTOP,
                name="Desktop System Banner",
                enabled=True,
                config={"sound": "Glass", "sound_enabled": True},
                created_at=now,
                updated_at=now,
            ),
            NotificationChannel(
                id=f"chan-{uuid.uuid4().hex[:8]}",
                workspace_id=workspace_id,
                channel_type=ChannelType.TELEGRAM,
                name="Telegram Bot",
                enabled=False,
                config={"bot_token": "", "chat_id": ""},
                created_at=now,
                updated_at=now,
            ),
            NotificationChannel(
                id=f"chan-{uuid.uuid4().hex[:8]}",
                workspace_id=workspace_id,
                channel_type=ChannelType.WEBHOOK,
                name="Outgoing Webhook",
                enabled=False,
                config={"url": "", "format": "generic", "secret": ""},
                created_at=now,
                updated_at=now,
            ),
            NotificationChannel(
                id=f"chan-{uuid.uuid4().hex[:8]}",
                workspace_id=workspace_id,
                channel_type=ChannelType.EMAIL,
                name="SMTP Email Relay",
                enabled=False,
                config={"smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "", "from_addr": "", "to_addrs": []},
                created_at=now,
                updated_at=now,
            ),
        ]
        for ch in defaults:
            self.save_channel(ch)
        return defaults

    def list_channels(self, workspace_id: str) -> list[NotificationChannel]:
        """Lists configured channels for a workspace."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM notification_channels WHERE workspace_id = ? ORDER BY channel_type ASC",
            (workspace_id,),
        ).fetchall()
        return [self._row_to_channel(r) for r in rows]

    def get_channel(self, workspace_id: str, channel_type: ChannelType | str) -> NotificationChannel | None:
        """Retrieves a single channel by workspace and channel type."""
        ctype = channel_type.value if isinstance(channel_type, ChannelType) else str(channel_type).lower().strip()
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM notification_channels WHERE workspace_id = ? AND channel_type = ?",
            (workspace_id, ctype),
        ).fetchone()
        return self._row_to_channel(row) if row else None

    def save_channel(self, channel: NotificationChannel) -> NotificationChannel:
        """Inserts or updates a delivery channel configuration."""
        from datetime import datetime, timezone
        channel.updated_at = datetime.now(timezone.utc).isoformat()
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO notification_channels (
                    id, workspace_id, channel_type, name, enabled, config, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    channel.id,
                    channel.workspace_id,
                    channel.channel_type.value if isinstance(channel.channel_type, ChannelType) else str(channel.channel_type),
                    channel.name,
                    1 if channel.enabled else 0,
                    json.dumps(channel.config),
                    channel.created_at,
                    channel.updated_at,
                ),
            )
        return channel

    # -------------------------------------------------------------------------
    # Notification Routing Rules
    # -------------------------------------------------------------------------

    def ensure_default_rules(self, workspace_id: str) -> list[NotificationRule]:
        """Ensures default routing rules exist for the workspace."""
        existing = self.list_rules(workspace_id)
        if existing:
            return existing
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        defaults = [
            NotificationRule(
                id=f"rule-{uuid.uuid4().hex[:8]}",
                workspace_id=workspace_id,
                name="Urgent Approvals & Gate Failures",
                enabled=True,
                event_types=["approval_required", "task_failed", "action_failed"],
                min_priority=NotificationPriority.HIGH,
                channels=[ChannelType.IN_APP, ChannelType.DESKTOP, ChannelType.TELEGRAM, ChannelType.WEBHOOK],
                quiet_hours_enabled=False,
                created_at=now,
            ),
            NotificationRule(
                id=f"rule-{uuid.uuid4().hex[:8]}",
                workspace_id=workspace_id,
                name="Mission & Task Completions",
                enabled=True,
                event_types=["task_completed", "action_completed"],
                min_priority=NotificationPriority.NORMAL,
                channels=[ChannelType.IN_APP, ChannelType.DESKTOP],
                quiet_hours_enabled=False,
                created_at=now,
            ),
            NotificationRule(
                id=f"rule-{uuid.uuid4().hex[:8]}",
                workspace_id=workspace_id,
                name="Proactive Insights & Ambient Alerts",
                enabled=True,
                event_types=["insight"],
                min_priority=NotificationPriority.LOW,
                channels=[ChannelType.IN_APP],
                quiet_hours_enabled=False,
                created_at=now,
            ),
        ]
        for r in defaults:
            self.save_rule(r)
        return defaults

    def list_rules(self, workspace_id: str) -> list[NotificationRule]:
        """Lists routing rules for a workspace."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM notification_rules WHERE workspace_id = ? ORDER BY created_at ASC",
            (workspace_id,),
        ).fetchall()
        return [self._row_to_rule(r) for r in rows]

    def get_rule(self, workspace_id: str, rule_id: str) -> NotificationRule | None:
        """Retrieves a single routing rule."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM notification_rules WHERE workspace_id = ? AND id = ?",
            (workspace_id, rule_id),
        ).fetchone()
        return self._row_to_rule(row) if row else None

    def save_rule(self, rule: NotificationRule) -> NotificationRule:
        """Inserts or updates a notification rule."""
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO notification_rules (
                    id, workspace_id, name, enabled, event_types, min_priority,
                    channels, quiet_hours_enabled, quiet_hours_start, quiet_hours_end, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule.id,
                    rule.workspace_id,
                    rule.name,
                    1 if rule.enabled else 0,
                    json.dumps(rule.event_types),
                    rule.min_priority.value if isinstance(rule.min_priority, NotificationPriority) else str(rule.min_priority),
                    json.dumps([c.value if isinstance(c, ChannelType) else str(c) for c in rule.channels]),
                    1 if rule.quiet_hours_enabled else 0,
                    rule.quiet_hours_start,
                    rule.quiet_hours_end,
                    rule.created_at,
                ),
            )
        return rule

    def delete_rule(self, workspace_id: str, rule_id: str) -> bool:
        """Deletes a routing rule."""
        with self._transaction() as cursor:
            cursor.execute("DELETE FROM notification_rules WHERE workspace_id = ? AND id = ?", (workspace_id, rule_id))
            return cursor.rowcount > 0

    # -------------------------------------------------------------------------
    # Delivery Receipts
    # -------------------------------------------------------------------------

    def save_receipt(self, receipt: DeliveryReceipt) -> DeliveryReceipt:
        """Persists a channel delivery receipt."""
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO delivery_receipts (
                    id, notification_id, workspace_id, channel_type, status, detail, latency_ms, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.id,
                    receipt.notification_id,
                    receipt.workspace_id,
                    receipt.channel_type.value if isinstance(receipt.channel_type, ChannelType) else str(receipt.channel_type),
                    receipt.status.value if isinstance(receipt.status, DeliveryStatus) else str(receipt.status),
                    receipt.detail,
                    receipt.latency_ms,
                    receipt.timestamp,
                ),
            )
        return receipt

    def list_receipts(self, workspace_id: str, limit: int = 50) -> list[DeliveryReceipt]:
        """Retrieves recent delivery receipts for auditing."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM delivery_receipts WHERE workspace_id = ? ORDER BY timestamp DESC LIMIT ?",
            (workspace_id, max(1, limit)),
        ).fetchall()
        return [self._row_to_receipt(r) for r in rows]

    def get_delivery_receipts(self, notification_id: str) -> list[DeliveryReceipt]:
        """Retrieves delivery receipts for a specific notification."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM delivery_receipts WHERE notification_id = ? ORDER BY timestamp DESC",
            (notification_id,),
        ).fetchall()
        return [self._row_to_receipt(r) for r in rows]

    def update_receipt_status(
        self,
        notification_id: str,
        channel_type: ChannelType | str,
        status: DeliveryStatus | str,
        detail: str | None = None,
    ) -> DeliveryReceipt | None:
        """Updates the status and optional detail of an existing delivery receipt."""
        c_type = channel_type.value if isinstance(channel_type, ChannelType) else str(channel_type)
        s_val = status.value if isinstance(status, DeliveryStatus) else str(status)
        now = datetime.now(timezone.utc).isoformat()
        with self._transaction() as cursor:
            if detail is not None:
                cursor.execute(
                    """
                    UPDATE delivery_receipts
                    SET status = ?, detail = ?, timestamp = ?
                    WHERE notification_id = ? AND channel_type = ?
                    """,
                    (s_val, detail, now, notification_id, c_type),
                )
            else:
                cursor.execute(
                    """
                    UPDATE delivery_receipts
                    SET status = ?, timestamp = ?
                    WHERE notification_id = ? AND channel_type = ?
                    """,
                    (s_val, now, notification_id, c_type),
                )
            if cursor.rowcount > 0:
                conn = self._get_connection()
                row = conn.execute(
                    "SELECT * FROM delivery_receipts WHERE notification_id = ? AND channel_type = ?",
                    (notification_id, c_type),
                ).fetchone()
                return self._row_to_receipt(row) if row else None
        return None

    # -------------------------------------------------------------------------
    # Executive Briefings
    # -------------------------------------------------------------------------

    def save_briefing(self, briefing: NotificationBriefing) -> NotificationBriefing:
        """Persists an executive notification briefing."""
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO briefings (
                    id, workspace_id, title, summary, highlights, metrics, action_links, channels_dispatched, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    briefing.id,
                    briefing.workspace_id,
                    briefing.title,
                    briefing.summary,
                    json.dumps(briefing.highlights),
                    json.dumps(briefing.metrics),
                    json.dumps(briefing.action_links),
                    json.dumps(briefing.channels_dispatched),
                    briefing.created_at,
                ),
            )
        return briefing

    def list_briefings(self, workspace_id: str, limit: int = 20) -> list[NotificationBriefing]:
        """Lists saved executive briefings."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM briefings WHERE workspace_id = ? ORDER BY created_at DESC LIMIT ?",
            (workspace_id, max(1, limit)),
        ).fetchall()
        return [self._row_to_briefing(r) for r in rows]

    def get_briefing(self, briefing_id: str) -> NotificationBriefing | None:
        """Retrieves a single executive briefing."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM briefings WHERE id = ?", (briefing_id,)).fetchone()
        return self._row_to_briefing(row) if row else None

    # -------------------------------------------------------------------------
    # Row Mappers
    # -------------------------------------------------------------------------

    def _row_to_channel(self, row: sqlite3.Row) -> NotificationChannel:
        return NotificationChannel(
            id=row["id"],
            workspace_id=row["workspace_id"],
            channel_type=ChannelType.from_str(row["channel_type"]),
            name=row["name"],
            enabled=bool(row["enabled"]),
            config=json.loads(row["config"]) if row["config"] else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_rule(self, row: sqlite3.Row) -> NotificationRule:
        channels_raw = json.loads(row["channels"]) if row["channels"] else []
        return NotificationRule(
            id=row["id"],
            workspace_id=row["workspace_id"],
            name=row["name"],
            enabled=bool(row["enabled"]),
            event_types=json.loads(row["event_types"]) if row["event_types"] else ["*"],
            min_priority=NotificationPriority.from_str(row["min_priority"]),
            channels=[ChannelType.from_str(c) for c in channels_raw],
            quiet_hours_enabled=bool(row["quiet_hours_enabled"]),
            quiet_hours_start=row["quiet_hours_start"] or "22:00",
            quiet_hours_end=row["quiet_hours_end"] or "08:00",
            created_at=row["created_at"],
        )

    def _row_to_receipt(self, row: sqlite3.Row) -> DeliveryReceipt:
        return DeliveryReceipt(
            id=row["id"],
            notification_id=row["notification_id"],
            workspace_id=row["workspace_id"],
            channel_type=ChannelType.from_str(row["channel_type"]),
            status=DeliveryStatus.from_str(row["status"]),
            detail=row["detail"],
            latency_ms=float(row["latency_ms"]),
            timestamp=row["timestamp"],
        )

    def _row_to_briefing(self, row: sqlite3.Row) -> NotificationBriefing:
        return NotificationBriefing(
            id=row["id"],
            workspace_id=row["workspace_id"],
            title=row["title"],
            summary=row["summary"],
            highlights=json.loads(row["highlights"]) if row["highlights"] else [],
            metrics=json.loads(row["metrics"]) if row["metrics"] else {},
            action_links=json.loads(row["action_links"]) if row["action_links"] else [],
            channels_dispatched=json.loads(row["channels_dispatched"]) if row["channels_dispatched"] else [],
            created_at=row["created_at"],
        )

    def _row_to_notification(self, row: sqlite3.Row) -> Notification:
        keys = row.keys()
        primary_act = None
        if "primary_action" in keys and row["primary_action"]:
            try:
                primary_act = json.loads(row["primary_action"])
            except Exception:
                primary_act = row["primary_action"]

        secondary_act = None
        if "secondary_action" in keys and row["secondary_action"]:
            try:
                secondary_act = json.loads(row["secondary_action"])
            except Exception:
                secondary_act = row["secondary_action"]

        return Notification(
            id=row["id"],
            workspace_id=row["workspace_id"],
            type=NotificationType.from_str(row["type"]),
            title=row["title"],
            message=row["message"],
            priority=NotificationPriority.from_str(row["priority"]),
            status=NotificationStatus.from_str(row["status"]),
            link_view=row["link_view"],
            link_id=row["link_id"],
            action_required=bool(row["action_required"]),
            target_type=row["target_type"] if "target_type" in keys else None,
            target_id=row["target_id"] if "target_id" in keys else None,
            deep_link=row["deep_link"] if "deep_link" in keys else None,
            primary_action=primary_act,
            secondary_action=secondary_act,
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
        )

    def close(self) -> None:
        with self._conns_lock:
            for conn in list(self._all_conns):
                try:
                    conn.close()
                except Exception:
                    pass
            self._all_conns.clear()
        if hasattr(self._local, "conn"):
            self._local.conn = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
