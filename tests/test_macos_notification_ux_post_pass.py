"""
Tests for macOS Notification UX Post-Pass.
Verifies native notification delivery, elimination of Script Editor file picker traps,
Event Hub routing, sound options, and deep navigation target preservation.
"""
from __future__ import annotations

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
    NotificationType,
)
from aether.notifications.service import NotificationService
from aether.notifications.store import NotificationStore


@pytest.fixture
def temp_store(tmp_path):
    db_path = tmp_path / "test_notifications.db"
    return NotificationStore(db_path=db_path)


class MockEventHub:
    def __init__(self):
        self.published = []

    def publish(self, workspace_id: str, event_type: str, data: dict):
        self.published.append({
            "workspace_id": workspace_id,
            "event_type": event_type,
            "data": data,
        })


def test_deliver_desktop_with_event_hub_bypasses_osascript(temp_store):
    """
    When Event Hub is present (Aether Desktop app runtime), desktop delivery
    must route through Event Hub/SSE directly and NEVER spawn osascript,
    guaranteeing the official app icon and no file picker dialog.
    """
    event_hub = MockEventHub()
    dispatcher = NotificationDispatcher(store=temp_store, event_hub=event_hub)
    channel = NotificationChannel(
        id="chan-desktop-test",
        workspace_id="ws-test",
        channel_type=ChannelType.DESKTOP,
        name="Desktop Test",
    )
    notification = Notification(
        id="notif-100",
        workspace_id="ws-test",
        type=NotificationType.APPROVAL_REQUIRED,
        title="Mission Approval Needed",
        message="Please review social post draft before publish",
        link_view="missions",
        link_id="msn-social-01",
    )

    with patch("subprocess.run") as mock_subproc:
        status, detail = dispatcher._deliver_desktop(channel, notification)
        # subprocess.run must NOT be called because event_hub is present
        mock_subproc.assert_not_called()

    assert status == DeliveryStatus.SENT
    assert "Event Hub" in detail


def test_deliver_desktop_headless_macos_uses_system_events(temp_store):
    """
    In headless macOS fallback (event_hub is None), AppleScript must explicitly target
    'System Events' so that macOS never attributes the banner to Script Editor
    and never opens an Open File dialog on banner click.
    """
    dispatcher = NotificationDispatcher(store=temp_store, event_hub=None)
    channel = NotificationChannel(
        id="chan-desktop-test",
        workspace_id="ws-test",
        channel_type=ChannelType.DESKTOP,
        name="Desktop Test",
        config={"sound_enabled": True, "sound": "Glass"},
    )
    notification = Notification(
        id="notif-101",
        workspace_id="ws-test",
        type=NotificationType.TASK_COMPLETED,
        title="Execution Finished",
        message="Hardware benchmark completed successfully",
        link_view="fabric",
        link_id="node-local",
    )

    with patch("sys.platform", "darwin"), patch("subprocess.run") as mock_subproc:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_subproc.return_value = mock_proc

        status, detail = dispatcher._deliver_desktop(channel, notification)

        mock_subproc.assert_called_once()
        cmd_args = mock_subproc.call_args[0][0]
        assert cmd_args[0] == "osascript"
        assert cmd_args[1] == "-e"
        script_text = cmd_args[2]
        # Must explicitly target System Events
        assert 'tell application "System Events" to display notification' in script_text
        assert 'sound name "Glass"' in script_text
        assert status == DeliveryStatus.SENT
        assert "System Events" in detail


def test_test_channel_publishes_to_event_hub(temp_store):
    """
    test_channel for DESKTOP channel should emit a notification event to Event Hub
    so the live UI / Companion receives immediate feedback.
    """
    event_hub = MockEventHub()
    dispatcher = NotificationDispatcher(store=temp_store, event_hub=event_hub)

    receipt = dispatcher.test_channel(workspace_id="ws-test", channel_type=ChannelType.DESKTOP)
    assert receipt.status == DeliveryStatus.SENT
    assert receipt.channel_type == ChannelType.DESKTOP

    # Check that Event Hub received the notification event
    notif_events = [e for e in event_hub.published if e["event_type"] == "notification"]
    assert len(notif_events) >= 1
    event_data = notif_events[0]["data"]
    assert "Aether Fabric Channel Verification" in event_data["title"]


def test_notification_service_emits_navigation_target_payload(temp_store):
    """
    Verifies that link_view, link_id, priority, and metadata are properly preserved
    and published via Event Hub for front-end native deep linking.
    """
    event_hub = MockEventHub()
    service = NotificationService(store=temp_store, event_hub=event_hub)

    notif = service.notify_approval(
        workspace_id="ws-test",
        title="Approval Required: Deploy to Staging",
        message="Aether requires your approval to proceed with deployment",
        action_id="act-99",
        execution_id="exec-42",
        prompt="Review social media post draft before broadcast",
        risk_tier="high",
        link_view="missions",
        link_id="msn-deploy-99",
    )

    assert notif.link_view == "missions"
    assert notif.link_id == "msn-deploy-99"
    assert notif.action_required is True

    # Check published SSE payload
    published = [e for e in event_hub.published if e["event_type"] == "notification"]
    assert len(published) == 1
    data = published[0]["data"]
    assert data["link_view"] == "missions"
    assert data["link_id"] == "msn-deploy-99"
    assert data["action_payload"]["action_id"] == "act-99"


def test_desktop_notification_sound_disabled(temp_store):
    """
    When sound_enabled is False, no sound option should be included.
    """
    dispatcher = NotificationDispatcher(store=temp_store, event_hub=None)
    channel = NotificationChannel(
        id="chan-silent",
        workspace_id="ws-test",
        channel_type=ChannelType.DESKTOP,
        name="Desktop Silent",
        config={"sound_enabled": False},
    )
    notification = Notification(
        id="notif-102",
        workspace_id="ws-test",
        type=NotificationType.INSIGHT,
        title="Quiet Notification",
        message="No sound banner",
    )

    with patch("sys.platform", "darwin"), patch("subprocess.run") as mock_subproc:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_subproc.return_value = mock_proc

        dispatcher._deliver_desktop(channel, notification)
        script_text = mock_subproc.call_args[0][0][2]
        assert "sound name" not in script_text
