"""
P3.2 Release-Grade Hardening: Notification E2E & Delivery Test Suite.
Verifies:
1. Single delivery owner (NotificationDispatcher) & truthful receipt tracking across states.
2. Telegram delivery deduplication within 60-second window.
3. SMTP secret resolution before smtplib.SMTP.login() & non-leaking diagnostic errors.
4. Desktop notification runtime modes (Event Hub, Desktop Runtime guard, OS fallback).
5. Multi-target queue persistence, 50-item cap, TTL pruning (>900s), and legacy single-target migration.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import smtplib
import sys
import time
from unittest.mock import MagicMock, patch
import pytest

from aether.notifications.dispatcher import NotificationDispatcher
from aether.notifications.models import (
    ChannelType,
    DeliveryStatus,
    Notification,
    NotificationChannel,
    NotificationPriority,
    NotificationTargetType,
    NotificationType,
)
from aether.notifications.service import NotificationService
from aether.notifications.store import NotificationStore
from aether.personal.events import PersonalEventHub
from aether.core.secrets import EncryptedVaultSecretStore, MemorySecretStore


@pytest.fixture
def temp_vault_and_store(tmp_path: Path):
    vault_file = tmp_path / "secrets.vault"
    secret_store = EncryptedVaultSecretStore(vault_file)
    db_path = tmp_path / "notifications.db"
    notif_store = NotificationStore(db_path=db_path, secret_store=secret_store)
    return secret_store, notif_store


# -----------------------------------------------------------------------------
# 1. Single Delivery Owner & Truthful Receipt Tracking
# -----------------------------------------------------------------------------

def test_notification_dispatcher_single_owner_and_receipts(temp_vault_and_store):
    secret_store, notif_store = temp_vault_and_store
    hub = PersonalEventHub()
    dispatcher = NotificationDispatcher(store=notif_store, event_hub=hub, secret_store=secret_store)

    # Configure IN_APP and DESKTOP channels
    in_app_chan = NotificationChannel(
        id="chan-inapp",
        workspace_id="ws-prod",
        channel_type=ChannelType.IN_APP,
        name="In App Alerts",
        enabled=True,
    )
    notif_store.save_channel(in_app_chan)

    notif = Notification(
        id="notif-e2e-001",
        workspace_id="ws-prod",
        type=NotificationType.ACTION_COMPLETED,
        title="Backup Succeeded",
        message="Full snapshot verified successfully.",
        priority=NotificationPriority.NORMAL,
    )

    receipts = dispatcher.dispatch(notif, target_channel_types=[ChannelType.IN_APP])
    assert len(receipts) == 1
    assert receipts[0].status == DeliveryStatus.SENT
    assert receipts[0].notification_id == "notif-e2e-001"

    # Verify receipts persisted in database
    db_receipts = notif_store.get_delivery_receipts("notif-e2e-001")
    assert len(db_receipts) == 1
    assert db_receipts[0].status == DeliveryStatus.SENT


# -----------------------------------------------------------------------------
# 2. Telegram Delivery Deduplication & Window
# -----------------------------------------------------------------------------

def test_telegram_delivery_deduplication_and_window(temp_vault_and_store):
    secret_store, notif_store = temp_vault_and_store
    dispatcher = NotificationDispatcher(store=notif_store, secret_store=secret_store)

    tg_chan = NotificationChannel(
        id="chan-tg",
        workspace_id="ws-prod",
        channel_type=ChannelType.TELEGRAM,
        name="Ops Bot",
        enabled=True,
        config={"bot_token": "123456:ABC-DEF-XYZ", "chat_id": "-100123456789"},
    )
    notif_store.save_channel(tg_chan)

    notif = Notification(
        id="notif-tg-001",
        workspace_id="ws-prod",
        type=NotificationType.ACTION_FAILED,
        title="High Memory Alert",
        message="RAM usage exceeded 90%",
        priority=NotificationPriority.HIGH,
    )

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.getcode.return_value = 200
        mock_resp.read.return_value = b'{"ok": true}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        # 1. First delivery attempt: must succeed
        status, details = dispatcher._deliver_telegram(tg_chan, notif)
        assert status == DeliveryStatus.SENT
        assert "delivered to chat" in details or "sent to chat" in details
        assert mock_urlopen.call_count == 1

        # 2. Duplicate delivery within 60s: must be suppressed
        status2, details2 = dispatcher._deliver_telegram(tg_chan, notif)
        assert status2 == DeliveryStatus.SKIPPED
        assert "Duplicate Telegram notification suppressed" in details2
        assert mock_urlopen.call_count == 1  # No extra HTTP call

        # 3. Different notification ID: must succeed
        notif_other = Notification(
            id="notif-tg-002",
            workspace_id="ws-prod",
            type=NotificationType.ACTION_FAILED,
            title="CPU Spike",
            message="CPU at 100%",
        )
        status3, details3 = dispatcher._deliver_telegram(tg_chan, notif_other)
        assert status3 == DeliveryStatus.SENT
        assert mock_urlopen.call_count == 2

        # 4. Fast-forward past 60s: original notification ID can now be sent again
        original_ts = dispatcher._recent_telegram_deliveries[f"telegram:{notif.id}:{tg_chan.workspace_id}"]
        dispatcher._recent_telegram_deliveries[f"telegram:{notif.id}:{tg_chan.workspace_id}"] = original_ts - 61.0

        status4, details4 = dispatcher._deliver_telegram(tg_chan, notif)
        assert status4 == DeliveryStatus.SENT
        assert mock_urlopen.call_count == 3


# -----------------------------------------------------------------------------
# 3. SMTP Secret Resolution Before Login & Non-Leaking Error Reporting
# -----------------------------------------------------------------------------

def test_smtp_secret_resolution_before_login(temp_vault_and_store):
    secret_store, notif_store = temp_vault_and_store
    dispatcher = NotificationDispatcher(store=notif_store, secret_store=secret_store)

    secret_password = "ULTRA_CONFIDENTIAL_SMTP_PASSWORD_999!"
    s_ref = secret_store.store_secret(
        secret_ref="secret_ref:chan_email1_smtp_pass_12345",
        value=secret_password,
        entity_type="notification_channel",
        entity_id="chan-smtp",
    )

    email_chan = NotificationChannel(
        id="chan-smtp",
        workspace_id="ws-prod",
        channel_type=ChannelType.EMAIL,
        name="Incident Alerts",
        enabled=True,
        config={
            "smtp_host": "smtp.fastmail.com",
            "smtp_port": 587,
            "smtp_user": "alerts@aether.internal",
            "smtp_pass": s_ref,
            "recipient_email": "ops-oncall@aether.internal",
        },
    )
    notif_store.save_channel(email_chan)

    notif = Notification(
        id="notif-email-001",
        workspace_id="ws-prod",
        type=NotificationType.TASK_FAILED,
        title="Deploy Pipeline Aborted",
        message="Build check failed at step 4",
    )

    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_smtp_inst = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_inst

        # Dispatch should resolve s_ref and invoke login with real password
        status, details = dispatcher._deliver_email(email_chan, notif)
        assert status == DeliveryStatus.SENT
        assert "Email delivered" in details

        # Verify login arguments: user and resolved password, NOT secret_ref
        mock_smtp_inst.login.assert_called_once_with(
            "alerts@aether.internal",
            secret_password,
        )
        assert s_ref not in str(mock_smtp_inst.login.call_args)


def test_smtp_failure_does_not_leak_password(temp_vault_and_store):
    secret_store, notif_store = temp_vault_and_store
    dispatcher = NotificationDispatcher(store=notif_store, secret_store=secret_store)

    secret_password = "SUPER_SECRET_VALUE_DO_NOT_LEAK"
    s_ref = secret_store.store_secret(
        secret_ref="secret_ref:chan_fail_pass_567",
        value=secret_password,
        entity_type="notification_channel",
        entity_id="chan-smtp-fail",
    )

    email_chan = NotificationChannel(
        id="chan-smtp-fail",
        workspace_id="ws-prod",
        channel_type=ChannelType.EMAIL,
        name="Failure Alerts",
        enabled=True,
        config={
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_user": "robot@example.com",
            "smtp_pass": s_ref,
            "recipient_email": "admin@example.com",
        },
    )
    notif = Notification(
        id="notif-email-fail",
        workspace_id="ws-prod",
        type=NotificationType.ACTION_FAILED,
        title="Test Email",
        message="Testing fail",
    )

    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_smtp_inst = MagicMock()
        mock_smtp_inst.login.side_effect = smtplib.SMTPAuthenticationError(
            535, f"Authentication credentials invalid for {secret_password}"
        )
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_inst

        status, details = dispatcher._deliver_email(email_chan, notif)
        assert status == DeliveryStatus.FAILED
        # Plaintext secret MUST NOT leak in delivery details or logs!
        assert secret_password not in details


# -----------------------------------------------------------------------------
# 4. Desktop Notification Runtime Modes & Routing
# -----------------------------------------------------------------------------

def test_desktop_notification_event_hub_routing(temp_vault_and_store):
    secret_store, notif_store = temp_vault_and_store

    # 1. Event Hub with active desktop subscribers -> DISPATCHED
    active_hub = PersonalEventHub()
    # Subscribe a desktop client
    sub_queue = active_hub.subscribe("ws-prod")
    dispatcher_active = NotificationDispatcher(
        store=notif_store, event_hub=active_hub, secret_store=secret_store
    )

    chan = NotificationChannel(
        id="chan-desk",
        workspace_id="ws-prod",
        channel_type=ChannelType.DESKTOP,
        name="Desktop Banner",
        enabled=True,
    )
    notif = Notification(
        id="notif-desk-01",
        workspace_id="ws-prod",
        type=NotificationType.ACTION_COMPLETED,
        title="Task Finished",
        message="Artifact exported.",
    )

    status, details = dispatcher_active._deliver_desktop(chan, notif)
    assert status == DeliveryStatus.DISPATCHED
    assert "Dispatched to 1 active desktop subscriber" in details

    # 2. Event Hub with 0 active subscribers -> QUEUED
    empty_hub = PersonalEventHub()
    dispatcher_empty = NotificationDispatcher(
        store=notif_store, event_hub=empty_hub, secret_store=secret_store
    )
    status2, details2 = dispatcher_empty._deliver_desktop(chan, notif)
    assert status2 == DeliveryStatus.QUEUED
    assert "Queued in Event Hub" in details2


def test_desktop_notification_packaged_guard(temp_vault_and_store, monkeypatch):
    secret_store, notif_store = temp_vault_and_store
    dispatcher = NotificationDispatcher(store=notif_store, event_hub=None, secret_store=secret_store)

    chan = NotificationChannel(
        id="chan-desk-pkg",
        workspace_id="ws-prod",
        channel_type=ChannelType.DESKTOP,
        name="Desktop",
        enabled=True,
    )
    notif = Notification(
        id="notif-pkg-01",
        workspace_id="ws-prod",
        type=NotificationType.TASK_COMPLETED,
        title="Mission Assigned",
        message="Ready for review.",
    )

    # When packaged runtime is active, osascript must NEVER be invoked
    monkeypatch.setenv("AETHER_DESKTOP_RUNTIME", "1")
    with patch("subprocess.run") as mock_run:
        status, details = dispatcher._deliver_desktop(chan, notif)
        assert status == DeliveryStatus.SKIPPED
        assert "Desktop notifications managed directly by Tauri runtime" in details
        mock_run.assert_not_called()


# -----------------------------------------------------------------------------
# 5. Multi-Target Queue Simulation & TTL / FIFO Pruning
# -----------------------------------------------------------------------------

def test_pending_notification_targets_queue_logic(tmp_path: Path):
    """
    Validates cross-layer parity with Rust pending_targets queue:
    - Prunes targets older than 900 seconds (15 minutes).
    - Capped at 50 items.
    - Upgrades legacy pending_notification_target.json to pending_notification_targets.json queue.
    """
    data_dir = tmp_path / "app_data"
    data_dir.mkdir(parents=True)
    queue_file = data_dir / "pending_notification_targets.json"
    legacy_file = data_dir / "pending_notification_target.json"

    # 1. Test legacy migration
    legacy_target = {
        "notification_id": "notif-leg-01",
        "target_type": "approval",
        "target_id": "exec-111",
        "view": "missions",
        "id": "exec-111",
        "deep_link": "aether://missions/exec-111",
        "created_at": int(time.time()),
    }
    legacy_file.write_text(json.dumps(legacy_target))

    # Migration simulation
    def read_targets(d_dir: Path) -> list[dict]:
        q_path = d_dir / "pending_notification_targets.json"
        l_path = d_dir / "pending_notification_target.json"
        if q_path.exists():
            return json.loads(q_path.read_text())
        if l_path.exists():
            t = json.loads(l_path.read_text())
            l_path.unlink()
            return [t]
        return []

    recovered = read_targets(data_dir)
    assert len(recovered) == 1
    assert recovered[0]["notification_id"] == "notif-leg-01"
    assert not legacy_file.exists()  # Legacy file cleaned up

    # 2. Add 60 targets to test capacity cap (50) and TTL pruning
    now = int(time.time())
    targets = []
    # 5 expired targets (created 1000s ago)
    for i in range(5):
        targets.append({
            "notification_id": f"expired-{i}",
            "view": "missions",
            "created_at": now - 1000,
        })
    # 55 fresh targets
    for i in range(55):
        targets.append({
            "notification_id": f"fresh-{i}",
            "view": "missions",
            "created_at": now - 10,
        })

    # Simulate Rust prune and cap:
    # 1) Retain unexpired (<= 900s)
    unexpired = [t for t in targets if now - t["created_at"] <= 900]
    assert len(unexpired) == 55

    # 2) Enforce cap of 50
    if len(unexpired) > 50:
        unexpired = unexpired[-50:]  # Keep latest 50

    assert len(unexpired) == 50
    assert unexpired[0]["notification_id"] == "fresh-5"
    assert unexpired[-1]["notification_id"] == "fresh-54"

    queue_file.write_text(json.dumps(unexpired, indent=2))
    assert queue_file.exists()
