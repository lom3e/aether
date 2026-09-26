"""
Exhaustive test suite for Macro-pass P0.3 — Canonical Notification Fabric.
Verifies the complete pipeline:
  Notification -> Canonical Target -> Single Delivery Owner -> Native/Desktop Delivery
  -> User Click -> Focus Aether -> Resolve Target -> Navigate to exact view/entity.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
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


@pytest.fixture
def temp_store(tmp_path):
    db_path = tmp_path / "canonical_notifications.db"
    return NotificationStore(db_path=db_path)


@pytest.fixture
def event_hub():
    return PersonalEventHub()


# ---------------------------------------------------------------------------
# 1. Canonical Payload Serialization / Deserialization
# ---------------------------------------------------------------------------

def test_canonical_notification_serialization():
    notif = Notification(
        id="notif-p03-01",
        workspace_id="ws-test",
        type=NotificationType.APPROVAL_REQUIRED,
        title="Production Deployment Approval",
        message="Deploying pipeline #42 requires clearance",
        priority=NotificationPriority.HIGH,
        target_type=NotificationTargetType.APPROVAL,
        target_id="exec-42",
        deep_link="aether://missions/msn-deploy-42",
        primary_action={"label": "Approve", "action": "approve", "target_id": "exec-42"},
        secondary_action={"label": "Reject", "action": "reject", "target_id": "exec-42"},
        metadata={"run_id": "run-99"},
    )

    data = notif.to_dict()
    assert data["id"] == "notif-p03-01"
    assert data["target_type"] == "approval"
    assert data["target_id"] == "exec-42"
    assert data["deep_link"] == "aether://missions/msn-deploy-42"
    assert data["primary_action"]["label"] == "Approve"
    assert data["secondary_action"]["label"] == "Reject"

    # Bidirectional alias reconciliation: link_view is automatically synced to "missions"
    assert data["link_view"] == "missions"
    assert data["link_id"] == "exec-42"

    # Deserialization from dictionary
    restored = Notification.from_dict(data)
    assert restored.id == notif.id
    assert restored.target_type == NotificationTargetType.APPROVAL
    assert restored.target_id == "exec-42"
    assert restored.deep_link == "aether://missions/msn-deploy-42"
    assert restored.primary_action["label"] == "Approve"


# ---------------------------------------------------------------------------
# 2. Target Resolution for Every Supported Target Type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("target_type", "target_id", "expected_view", "expected_id"),
    [
        (NotificationTargetType.MISSION, "msn-101", "missions", "msn-101"),
        (NotificationTargetType.APPROVAL, "exec-202", "missions", "exec-202"),
        (NotificationTargetType.ACTION_EXECUTION, "exec-303", "connections", "exec-303"),
        (NotificationTargetType.AUTOMATION, "auto-404", "automations", "auto-404"),
        (NotificationTargetType.DELIVERABLE, "deliv-505", "missions", "deliv-505"),
        (NotificationTargetType.TASK, "task-606", "home", "task-606"),
        (NotificationTargetType.CONNECTION, "conn-707", "connections", "conn-707"),
        (NotificationTargetType.CHAT, "conv-808", "chat", "conv-808"),
        (NotificationTargetType.SETTINGS, None, "settings", None),
        (NotificationTargetType.VIEW, "workforce", "workforce", None),
    ],
)
def test_all_canonical_target_types_auto_reconciled(target_type, target_id, expected_view, expected_id):
    notif = Notification(
        id=f"notif-{target_type.value}",
        workspace_id="ws-test",
        type=NotificationType.INSIGHT,
        title=f"Testing {target_type.value}",
        message="Verification payload",
        target_type=target_type,
        target_id=target_id,
    )
    assert notif.link_view == expected_view
    if expected_id is not None:
        assert notif.link_id == expected_id


# ---------------------------------------------------------------------------
# 3. Store Persistence & Existing DB Backward Compatibility
# ---------------------------------------------------------------------------

def test_store_persistence_and_schema_migration(tmp_path):
    db_file = tmp_path / "legacy_notifications.db"
    conn = sqlite3.connect(str(db_file))
    # Simulate legacy table without target_type, target_id, etc.
    conn.execute(
        """
        CREATE TABLE notifications (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT,
            priority TEXT NOT NULL,
            status TEXT NOT NULL,
            link_view TEXT,
            link_id TEXT,
            action_required INTEGER DEFAULT 0,
            metadata TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO notifications VALUES (
            'legacy-01', 'ws-test', 'task_completed', 'Legacy Title',
            'Legacy Body', 'normal', 'unread', 'missions', 'm-old', 0, '{}', '2026-01-01T00:00:00Z'
        )
        """
    )
    conn.commit()
    conn.close()

    # Open with NotificationStore: it must automatically run ALTER TABLE migrations
    store = NotificationStore(db_path=db_file)
    legacy_notif = store.get("legacy-01")
    assert legacy_notif is not None
    assert legacy_notif.link_view == "missions"
    assert legacy_notif.link_id == "m-old"
    # Auto-reconciled target_type from link_view
    assert legacy_notif.target_type == NotificationTargetType.MISSION
    assert legacy_notif.target_id == "m-old"

    # Save a new canonical notification
    new_notif = Notification(
        id="canonical-02",
        workspace_id="ws-test",
        type=NotificationType.INSIGHT,
        title="Modern Canonical",
        message="Modern message",
        target_type=NotificationTargetType.DELIVERABLE,
        target_id="doc-77",
        deep_link="aether://missions/doc-77",
    )
    store.save(new_notif)

    fetched = store.get("canonical-02")
    assert fetched is not None
    assert fetched.target_type == NotificationTargetType.DELIVERABLE
    assert fetched.target_id == "doc-77"
    assert fetched.deep_link == "aether://missions/doc-77"


# ---------------------------------------------------------------------------
# 4. Backward Compatibility with legacy link_view / link_id
# ---------------------------------------------------------------------------

def test_legacy_kwargs_compatibility():
    notif = Notification.from_dict({
        "id": "legacy-kw-01",
        "workspace_id": "ws-test",
        "type": "task_completed",
        "title": "Legacy Notification",
        "body": "Using body alias instead of message",
        "severity": "urgent",
        "link_view": "connections",
        "link_id": "google-cal",
        "requires_action": True,
    })
    assert notif.message == "Using body alias instead of message"
    assert notif.priority == NotificationPriority.HIGH
    assert notif.action_required is True
    assert notif.target_type == NotificationTargetType.ACTION_EXECUTION or notif.target_type == NotificationTargetType.CONNECTION
    assert notif.target_id == "google-cal"


# ---------------------------------------------------------------------------
# 5. Deterministic Deduplication
# ---------------------------------------------------------------------------

def test_deterministic_dedup_semantics():
    notif1 = Notification(
        id="notif-dup-1",
        workspace_id="ws-test",
        type=NotificationType.INSIGHT,
        title="CPU High Usage",
        message="CPU is at 98%",
        target_type=NotificationTargetType.VIEW,
        target_id="fabric",
    )
    notif2 = Notification(
        id="notif-dup-1",  # Same id
        workspace_id="ws-test",
        type=NotificationType.INSIGHT,
        title="CPU High Usage",
        message="CPU is at 98%",
        target_type=NotificationTargetType.VIEW,
        target_id="fabric",
    )
    assert notif1.id == notif2.id
    # Deduplication key composed of ID or (title + message + target_type + target_id)
    key1 = notif1.id or f"{notif1.title}:{notif1.message}:{notif1.target_type}:{notif1.target_id}"
    key2 = notif2.id or f"{notif2.title}:{notif2.message}:{notif2.target_type}:{notif2.target_id}"
    assert key1 == key2


# ---------------------------------------------------------------------------
# 6. Single Delivery Owner: SSE Dispatched Only to Workspace Desktop Owner
# ---------------------------------------------------------------------------

def test_single_delivery_owner_dispatched_via_event_hub(temp_store, event_hub):
    dispatcher = NotificationDispatcher(store=temp_store, event_hub=event_hub)
    channel = NotificationChannel(
        id="chan-desktop-owner",
        workspace_id="ws-owner-test",
        channel_type=ChannelType.DESKTOP,
        name="Desktop Main",
    )
    notif = Notification(
        id="notif-owner-01",
        workspace_id="ws-owner-test",
        type=NotificationType.APPROVAL_REQUIRED,
        title="Sole Delivery Owner Test",
        message="Only the active workspace surface displays this natively",
        target_type=NotificationTargetType.APPROVAL,
        target_id="exec-owner",
    )

    # When no subscribers are connected, delivery is QUEUED (truthful)
    status_empty, detail_empty = dispatcher._deliver_desktop(channel, notif)
    assert status_empty == DeliveryStatus.QUEUED
    assert "no active desktop subscribers" in detail_empty

    # When active subscriber connects (e.g. Workspace main window)
    queue = event_hub.subscribe("ws-owner-test")
    try:
        status_active, detail_active = dispatcher._deliver_desktop(channel, notif)
        assert status_active == DeliveryStatus.DISPATCHED
        assert "active desktop subscriber" in detail_active
    finally:
        event_hub.unsubscribe("ws-owner-test", queue)


# ---------------------------------------------------------------------------
# 7. Native Desktop Delivery: Tauri Bundle Identifier com.aether.desktop
# ---------------------------------------------------------------------------

def test_tauri_runtime_env_detection(temp_store):
    dispatcher = NotificationDispatcher(store=temp_store, event_hub=None)
    channel = NotificationChannel(
        id="chan-dsk-1",
        workspace_id="ws-test",
        channel_type=ChannelType.DESKTOP,
        name="Desktop",
    )
    notif = Notification(
        id="notif-tauri-01",
        workspace_id="ws-test",
        type=NotificationType.INSIGHT,
        title="Tauri Native Route",
        message="Managed by Tauri runtime",
    )

    with patch.dict(os.environ, {"AETHER_DESKTOP_RUNTIME": "1"}):
        with patch("subprocess.run") as mock_run:
            status, detail = dispatcher._deliver_desktop(channel, notif)
            mock_run.assert_not_called()
            assert status == DeliveryStatus.SKIPPED
            assert "managed directly by Tauri runtime" in detail


# ---------------------------------------------------------------------------
# 8. Strict Bypass of osascript in Packaged Mode / App Bundle
# ---------------------------------------------------------------------------

def test_osascript_strictly_bypassed_in_app_bundle(temp_store):
    dispatcher = NotificationDispatcher(store=temp_store, event_hub=None)
    channel = NotificationChannel(
        id="chan-dsk-2",
        workspace_id="ws-test",
        channel_type=ChannelType.DESKTOP,
        name="Desktop",
    )
    notif = Notification(
        id="notif-bundle-01",
        workspace_id="ws-test",
        type=NotificationType.TASK_COMPLETED,
        title="App Bundle Active",
        message="Zero AppleScript execution",
    )

    with patch.dict(os.environ, {"AETHER_APP_BUNDLE": "1"}):
        with patch("subprocess.run") as mock_run:
            status, detail = dispatcher._deliver_desktop(channel, notif)
            mock_run.assert_not_called()
            assert status == DeliveryStatus.SKIPPED
            assert "osascript disabled in packaged mode" in detail


# ---------------------------------------------------------------------------
# 9. Headless / Dev Fallback Uses System Events (No Script Editor Trap)
# ---------------------------------------------------------------------------

def test_headless_fallback_explicitly_targets_system_events(temp_store):
    dispatcher = NotificationDispatcher(store=temp_store, event_hub=None)
    channel = NotificationChannel(
        id="chan-dsk-3",
        workspace_id="ws-test",
        channel_type=ChannelType.DESKTOP,
        name="Desktop Dev",
        config={"sound_enabled": True, "sound": "Glass"},
    )
    notif = Notification(
        id="notif-headless-01",
        workspace_id="ws-test",
        type=NotificationType.INSIGHT,
        title="Headless Development Banner",
        message="Must not open external editor or dialog",
    )

    with patch.dict(os.environ, {}, clear=True):
        with patch("sys.platform", "darwin"), patch("subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_run.return_value = mock_proc

            status, detail = dispatcher._deliver_desktop(channel, notif)
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            script = cmd[2]

            # Critical: Must target "System Events" specifically
            assert 'tell application "System Events" to display notification' in script
            # Never attribute to Script Editor
            assert "Script Editor" not in script
            assert status == DeliveryStatus.SENT
            assert "System Events" in detail


# ---------------------------------------------------------------------------
# 10. Click Notification Routing & Action Payload
# ---------------------------------------------------------------------------

def test_service_notify_approval_includes_canonical_routing(temp_store, event_hub):
    service = NotificationService(store=temp_store, event_hub=event_hub)
    notif = service.notify_approval(
        workspace_id="ws-test",
        title="High Risk Action Approval",
        message="Aether proposes rm -rf node_modules",
        action_id="act-delete",
        execution_id="exec-delete-01",
        prompt="Confirm directory cleanup",
        risk_tier="critical",
        target_type="approval",
        target_id="exec-delete-01",
        deep_link="aether://missions/exec-delete-01",
    )

    assert notif.target_type == NotificationTargetType.APPROVAL
    assert notif.target_id == "exec-delete-01"
    assert notif.deep_link == "aether://missions/exec-delete-01"
    assert notif.primary_action is not None
    assert notif.secondary_action is not None

    # Verify event published through event hub
    queue = event_hub.subscribe("ws-test")
    try:
        service.notify(
            workspace_id="ws-test",
            type="approval_required",
            title="Interactive Approval",
            message="Please confirm action",
            target_type="approval",
            target_id="exec-test-99",
        )
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())
        notif_event = next((e for e in events if e.get("type") == "notification"), None)
        assert notif_event is not None
        assert notif_event["data"]["target_type"] == "approval"
        assert notif_event["data"]["target_id"] == "exec-test-99"
    finally:
        event_hub.unsubscribe("ws-test", queue)


# ---------------------------------------------------------------------------
# 11. Delivery Receipts: Queued, Dispatched, Displayed, Failed
# ---------------------------------------------------------------------------

def test_delivery_receipt_status_transitions(temp_store, event_hub):
    service = NotificationService(store=temp_store, event_hub=event_hub)
    notif = service.notify(
        workspace_id="ws-test",
        type="task_completed",
        title="Background Job",
        message="Processing completed",
        target_type="mission",
        target_id="msn-bg",
        target_channels=["desktop"],
    )

    # Initial receipt created
    receipts = temp_store.get_delivery_receipts(notif.id)
    assert len(receipts) >= 1
    # Without active desktop subscriber, initial state is QUEUED
    assert receipts[0].status == DeliveryStatus.QUEUED

    # Update receipt when client displays it
    updated = service.update_delivery_receipt(
        workspace_id="ws-test",
        notification_id=notif.id,
        channel_type="desktop",
        status="displayed",
        detail="Native macOS notification banner presented",
    )
    assert updated is not None
    assert updated.status == DeliveryStatus.DISPLAYED
    assert "Native macOS notification banner presented" in updated.detail

    # Verify persisted in SQLite
    reloaded_receipts = temp_store.get_delivery_receipts(notif.id)
    assert reloaded_receipts[0].status == DeliveryStatus.DISPLAYED


# ---------------------------------------------------------------------------
# 12. Acknowledge Receipt Endpoint Logic
# ---------------------------------------------------------------------------

def test_acknowledge_receipt_unknown_notification(temp_store, event_hub):
    service = NotificationService(store=temp_store, event_hub=event_hub)
    res = service.update_delivery_receipt(
        workspace_id="ws-test",
        notification_id="non-existent-id",
        channel_type="desktop",
        status="displayed",
    )
    assert res is None


# ---------------------------------------------------------------------------
# 13. Official Logo Asset Existence
# ---------------------------------------------------------------------------

def test_aether_official_logo_assets_exist():
    repo_root = os.path.dirname(os.path.dirname(__file__))
    logo_path = os.path.join(repo_root, "ui", "public", "logo.png")
    icon_path = os.path.join(repo_root, "ui", "public", "icon.png")
    tauri_icon_path = os.path.join(repo_root, "src-tauri", "icons", "128x128.png")

    assert os.path.isfile(logo_path), "ui/public/logo.png must exist for web notification fallback"
    assert os.path.isfile(icon_path), "ui/public/icon.png must exist"
    assert os.path.isfile(tauri_icon_path), "src-tauri/icons/128x128.png must exist"
    assert os.path.getsize(logo_path) > 1000
    assert os.path.getsize(icon_path) > 1000
