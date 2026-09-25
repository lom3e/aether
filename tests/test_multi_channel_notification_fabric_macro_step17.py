"""
Tests for Macro-Step 17: Multi-Channel Notification Fabric (Phase D).
Verifies models, SQLite persistence, dispatcher engine, briefings,
action registry & executor, personal agent intents, and FastAPI endpoints.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

import pytest
from starlette.requests import Request

from aether.actions.registry import ActionRegistry
from aether.notifications import (
    ChannelType,
    DeliveryReceipt,
    DeliveryStatus,
    Notification,
    NotificationBriefing,
    NotificationChannel,
    NotificationDispatcher,
    NotificationPriority,
    NotificationRule,
    NotificationService,
    NotificationStatus,
    NotificationStore,
    NotificationType,
    is_in_quiet_hours,
)
from aether.personal.models import IntentTier
from aether.personal.service import PersonalAgentService
from aether.server.routes import (
    configure_notification_channel_route,
    configure_notification_rule_route,
    delete_notification_rule_route,
    dispatch_custom_notification_route,
    dispatch_notification_briefing_route,
    dispatch_test_notification_channel_route,
    list_notification_briefings_route,
    list_notification_channels_route,
    list_notification_deliveries_route,
    list_notification_rules_route,
)
from aether.workspace.workspace import Workspace


@pytest.fixture
def temp_workspace(tmp_path: Path):
    ws_dir = tmp_path / "test_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return Workspace(root=ws_dir)


class DummyAppState:
    def __init__(self, workspace: Any) -> None:
        self.workspace = workspace


class DummyApp:
    def __init__(self, workspace: Any) -> None:
        self.state = DummyAppState(workspace)


def create_dummy_request(workspace: Any, body: dict[str, Any] | None = None) -> Request:
    scope = {"type": "http", "app": DummyApp(workspace), "headers": []}
    req = Request(scope=scope)
    if body is not None:
        async def fake_json():
            return body
        req.json = fake_json
    return req


def test_models_and_enums():
    """Verify notification fabric domain models, enums, and dict conversions."""
    assert ChannelType.from_str("desktop") == ChannelType.DESKTOP
    assert ChannelType.from_str("WEBHOOK") == ChannelType.WEBHOOK
    assert ChannelType.from_str("unknown") == ChannelType.IN_APP

    assert DeliveryStatus.from_str("sent") == DeliveryStatus.SENT
    assert DeliveryStatus.from_str("FAILED") == DeliveryStatus.FAILED
    assert DeliveryStatus.from_str("skipped") == DeliveryStatus.SKIPPED

    chan = NotificationChannel(
        id="chan-1",
        workspace_id="test-ws",
        channel_type=ChannelType.DESKTOP,
        name="Desktop",
        enabled=True,
        config={"sound": "Glass"},
    )
    d = chan.to_dict()
    assert d["channel_type"] == "desktop"
    assert d["name"] == "Desktop"
    loaded = NotificationChannel.from_dict(d)
    assert loaded.id == "chan-1"
    assert loaded.channel_type == ChannelType.DESKTOP

    rule = NotificationRule(
        id="rule-1",
        workspace_id="test-ws",
        name="Urgent Rule",
        event_types=["approval_required"],
        min_priority=NotificationPriority.HIGH,
        channels=[ChannelType.DESKTOP, ChannelType.TELEGRAM],
        quiet_hours_enabled=True,
        quiet_hours_start="23:00",
        quiet_hours_end="07:00",
    )
    rd = rule.to_dict()
    assert rd["min_priority"] == "high"
    assert "desktop" in rd["channels"]
    loaded_rule = NotificationRule.from_dict(rd)
    assert loaded_rule.channels == [ChannelType.DESKTOP, ChannelType.TELEGRAM]

    receipt = DeliveryReceipt(
        id="rcpt-1",
        notification_id="notif-1",
        workspace_id="test-ws",
        channel_type=ChannelType.WEBHOOK,
        status=DeliveryStatus.SENT,
        detail="HTTP 200 OK",
        latency_ms=12.5,
    )
    rcpt_d = receipt.to_dict()
    assert rcpt_d["status"] == "sent"
    assert rcpt_d["latency_ms"] == 12.5

    briefing = NotificationBriefing(
        id="brf-1",
        workspace_id="test-ws",
        title="Weekly Status",
        summary="All systems nominal",
        highlights=["Zero errors", "100% SLA"],
        metrics={"uptime": 99.9},
        channels_dispatched=["desktop", "in_app"],
    )
    bd = briefing.to_dict()
    assert bd["title"] == "Weekly Status"
    assert len(bd["highlights"]) == 2


def test_notification_store_persistence():
    """Verify SQLite persistence for channels, rules, receipts, and briefings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "notifications.db"
        store = NotificationStore(db_path)

        # 1. Default channels seeding
        channels = store.ensure_default_channels("ws-alpha")
        assert len(channels) >= 5
        types = {c.channel_type for c in channels}
        assert ChannelType.IN_APP in types
        assert ChannelType.DESKTOP in types
        assert ChannelType.WEBHOOK in types

        # 2. Update channel
        desktop_ch = store.get_channel("ws-alpha", ChannelType.DESKTOP)
        assert desktop_ch is not None
        desktop_ch.enabled = False
        desktop_ch.config["sound"] = "Ping"
        store.save_channel(desktop_ch)

        reloaded = store.get_channel("ws-alpha", "desktop")
        assert reloaded is not None
        assert reloaded.enabled is False
        assert reloaded.config.get("sound") == "Ping"

        # 3. Rules seeding & updates
        rules = store.ensure_default_rules("ws-alpha")
        assert len(rules) >= 3

        custom_rule = NotificationRule(
            id="rule-custom",
            workspace_id="ws-alpha",
            name="Custom Webhook Trigger",
            event_types=["task_completed"],
            channels=[ChannelType.WEBHOOK],
        )
        store.save_rule(custom_rule)
        all_rules = store.list_rules("ws-alpha")
        assert any(r.id == "rule-custom" for r in all_rules)

        assert store.delete_rule("ws-alpha", "rule-custom") is True
        assert store.get_rule("ws-alpha", "rule-custom") is None

        # 4. Delivery receipts
        receipt = DeliveryReceipt(
            id="rcpt-audit-1",
            notification_id="notif-100",
            workspace_id="ws-alpha",
            channel_type=ChannelType.DESKTOP,
            status=DeliveryStatus.SENT,
            detail="Desktop notification triggered",
            latency_ms=8.4,
        )
        store.save_receipt(receipt)
        receipts = store.list_receipts("ws-alpha", limit=10)
        assert len(receipts) == 1
        assert receipts[0].id == "rcpt-audit-1"

        # 5. Briefings
        briefing = NotificationBriefing(
            id="brf-alpha",
            workspace_id="ws-alpha",
            title="Sprint Review",
            summary="Completed sprint goals.",
            highlights=["Feature A deployed", "Tests green"],
            metrics={"velocity": 42},
            channels_dispatched=["desktop", "in_app"],
        )
        store.save_briefing(briefing)
        briefings = store.list_briefings("ws-alpha")
        assert len(briefings) == 1
        assert store.get_briefing("brf-alpha") is not None

        store.close()


def test_dispatcher_quiet_hours_and_delivery():
    """Verify quiet hours logic and multi-channel delivery dispatching."""
    from datetime import datetime
    now_noon = datetime(2026, 9, 25, 12, 0, 0)
    now_midnight = datetime(2026, 9, 25, 0, 30, 0)

    # 22:00 to 08:00 overnight window
    assert is_in_quiet_hours("22:00", "08:00", now_midnight) is True
    assert is_in_quiet_hours("22:00", "08:00", now_noon) is False

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "notif_dispatch.db"
        store = NotificationStore(db_path)
        dispatcher = NotificationDispatcher(store=store)

        # Dispatch test alert to desktop
        receipt = dispatcher.test_channel("ws-beta", ChannelType.DESKTOP)
        assert receipt.channel_type == ChannelType.DESKTOP
        assert receipt.status in (DeliveryStatus.SENT, DeliveryStatus.SKIPPED)

        # Dispatch notification through rules
        notif = Notification(
            id="notif-live-1",
            workspace_id="ws-beta",
            type=NotificationType.TASK_COMPLETED,
            title="Mission Completed: Core Pipeline",
            message="All 5 milestones executed successfully.",
            priority=NotificationPriority.NORMAL,
        )
        receipts = dispatcher.dispatch(notif)
        assert len(receipts) >= 1
        sent_or_skipped = {r.status for r in receipts}
        assert DeliveryStatus.SENT in sent_or_skipped or DeliveryStatus.SKIPPED in sent_or_skipped

        store.close()


def test_notification_service_briefing_and_channels():
    """Verify NotificationService briefing dispatch and channel/rule management."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "service_test.db"
        store = NotificationStore(db_path)
        service = NotificationService(store=store)

        # Test briefing dispatch
        briefing = service.dispatch_briefing(
            workspace_id="ws-prod",
            title="EOD Operational Digest",
            summary="Autonomous swarm closed 12 issues and updated documentation.",
            highlights=["12 issues resolved", "0 test regressions"],
            metrics={"pass_rate": 100, "duration_m": 4.5},
            channels=["in_app", "desktop"],
        )
        assert briefing.title == "EOD Operational Digest"
        assert len(briefing.highlights) == 2
        assert len(service.list_briefings("ws-prod")) == 1

        # Test configure channel
        updated_chan = service.configure_channel(
            workspace_id="ws-prod",
            channel_type="webhook",
            enabled=True,
            config={"url": "https://hooks.slack.com/services/test/123", "format": "slack"},
        )
        assert updated_chan.enabled is True
        assert updated_chan.config.get("url") == "https://hooks.slack.com/services/test/123"

        # Test configure rule
        rule = service.configure_rule(
            workspace_id="ws-prod",
            name="Critical Alerts Rule",
            event_types=["task_failed"],
            min_priority="high",
            channels=["in_app", "desktop", "webhook"],
        )
        assert rule.name == "Critical Alerts Rule"
        assert len(service.get_rules("ws-prod")) >= 4

        # Test delivery history
        history = service.get_delivery_history("ws-prod", limit=10)
        assert len(history) >= 1

        store.close()


def test_action_registry_and_executor(temp_workspace: Workspace):
    """Verify registration and execution of all 7 notification fabric actions."""
    registry = ActionRegistry()
    assert registry.get("notifications.send_briefing") is not None
    assert registry.get("notifications.list_channels") is not None
    assert registry.get("notifications.configure_channel") is not None
    assert registry.get("notifications.test_channel") is not None
    assert registry.get("notifications.list_rules") is not None
    assert registry.get("notifications.configure_rule") is not None
    assert registry.get("notifications.get_delivery_history") is not None

    executor = temp_workspace.actions

    # 1. list_channels
    res_chan = executor.execute(
        action_id="notifications.list_channels",
        workspace_id=temp_workspace.id,
        input_data={},
        auto_approve=True,
    )
    assert res_chan.status.value == "success"
    assert len(res_chan.output_data["channels"]) >= 5

    # 2. configure_channel
    res_cfg = executor.execute(
        action_id="notifications.configure_channel",
        workspace_id=temp_workspace.id,
        input_data={"channel_type": "desktop", "enabled": True, "config": {"sound": "Glass"}},
        auto_approve=True,
    )
    assert res_cfg.status.value == "success"
    assert res_cfg.output_data["channel"]["channel_type"] == "desktop"

    # 3. test_channel
    res_test = executor.execute(
        action_id="notifications.test_channel",
        workspace_id=temp_workspace.id,
        input_data={"channel_type": "desktop"},
        auto_approve=True,
    )
    assert res_test.status.value == "success"
    assert res_test.output_data["receipt"]["channel_type"] == "desktop"

    # 4. send_briefing
    res_brf = executor.execute(
        action_id="notifications.send_briefing",
        workspace_id=temp_workspace.id,
        input_data={
            "title": "Action Execution Briefing",
            "summary": "Briefing executed successfully from action runner.",
            "highlights": ["Zero errors"],
        },
        auto_approve=True,
    )
    assert res_brf.status.value == "success"
    assert res_brf.output_data["briefing"]["title"] == "Action Execution Briefing"

    # 5. list_rules & configure_rule
    res_rules = executor.execute(
        action_id="notifications.list_rules",
        workspace_id=temp_workspace.id,
        input_data={},
        auto_approve=True,
    )
    assert res_rules.status.value == "success"
    assert len(res_rules.output_data["rules"]) >= 3

    res_new_rule = executor.execute(
        action_id="notifications.configure_rule",
        workspace_id=temp_workspace.id,
        input_data={"name": "Execution Alert", "event_types": ["action_failed"], "min_priority": "high"},
        auto_approve=True,
    )
    assert res_new_rule.status.value == "success"
    assert res_new_rule.output_data["rule"]["name"] == "Execution Alert"

    # 6. get_delivery_history
    res_hist = executor.execute(
        action_id="notifications.get_delivery_history",
        workspace_id=temp_workspace.id,
        input_data={"limit": 10},
        auto_approve=True,
    )
    assert res_hist.status.value == "success"
    assert len(res_hist.output_data["receipts"]) >= 1


def test_personal_agent_intents(temp_workspace: Workspace):
    """Verify PersonalAgentService intent classification for notification directives."""
    service = PersonalAgentService(
        store=temp_workspace.personal_store,
        action_executor=temp_workspace.actions,
        activity_service=temp_workspace.activity,
    )

    intent1 = service.classify_intent("Invia un briefing di notifica della missione")
    assert intent1.action_id == "notifications.send_briefing"
    assert intent1.tier == IntentTier.DO

    intent2 = service.classify_intent("Mostra i canali di notifica attivi")
    assert intent2.action_id == "notifications.list_channels"
    assert intent2.tier == IntentTier.ANSWER

    intent3 = service.classify_intent("Testa il canale notifiche desktop")
    assert intent3.action_id == "notifications.test_channel"
    assert intent3.action_args.get("channel_type") == "desktop"

    intent4 = service.classify_intent("Configura canale webhook per le notifiche")
    assert intent4.action_id == "notifications.configure_channel"
    assert intent4.action_args.get("channel_type") == "webhook"


@pytest.mark.asyncio
async def test_fastapi_notification_routes(temp_workspace: Workspace):
    """Verify all FastAPI routes for Notification Fabric."""
    # 1. list channels
    req = create_dummy_request(temp_workspace)
    channels = await list_notification_channels_route(req, workspace_id=temp_workspace.id)
    assert len(channels) >= 5

    # 2. configure channel
    req_cfg = create_dummy_request(
        temp_workspace,
        {"workspace_id": temp_workspace.id, "channel_type": "webhook", "enabled": True, "config": {"url": "http://example.com"}},
    )
    chan_res = await configure_notification_channel_route(req_cfg)
    assert chan_res["channel_type"] == "webhook"
    assert chan_res["enabled"] is True

    # 3. test channel
    req_test = create_dummy_request(temp_workspace)
    receipt_res = await dispatch_test_notification_channel_route(req_test, channel_type="desktop", workspace_id=temp_workspace.id)
    assert receipt_res["channel_type"] == "desktop"

    # 4. list rules & configure rule
    req_rules = create_dummy_request(temp_workspace)
    rules_res = await list_notification_rules_route(req_rules, workspace_id=temp_workspace.id)
    assert len(rules_res) >= 3

    req_new_rule = create_dummy_request(
        temp_workspace,
        {"workspace_id": temp_workspace.id, "name": "API Rule", "event_types": ["*"], "min_priority": "normal"},
    )
    new_rule_res = await configure_notification_rule_route(req_new_rule)
    assert new_rule_res["name"] == "API Rule"

    # delete rule
    req_del = create_dummy_request(temp_workspace)
    del_res = await delete_notification_rule_route(req_del, rule_id=new_rule_res["id"], workspace_id=temp_workspace.id)
    assert del_res["status"] == "ok"

    # 5. dispatch briefing
    req_brf = create_dummy_request(
        temp_workspace,
        {"workspace_id": temp_workspace.id, "title": "API Briefing", "summary": "Tested from endpoint."},
    )
    brf_res = await dispatch_notification_briefing_route(req_brf)
    assert brf_res["title"] == "API Briefing"

    # list briefings
    req_list_brf = create_dummy_request(temp_workspace)
    briefings_list = await list_notification_briefings_route(req_list_brf, workspace_id=temp_workspace.id)
    assert len(briefings_list) == 1

    # 6. list deliveries
    req_deliv = create_dummy_request(temp_workspace)
    deliveries = await list_notification_deliveries_route(req_deliv, workspace_id=temp_workspace.id)
    assert len(deliveries) >= 1

    # 7. dispatch custom notification
    req_custom = create_dummy_request(
        temp_workspace,
        {
            "workspace_id": temp_workspace.id,
            "type": "task_completed",
            "title": "Custom Alert",
            "message": "Direct dispatch test",
            "priority": "normal",
        },
    )
    custom_res = await dispatch_custom_notification_route(req_custom)
    assert custom_res["title"] == "Custom Alert"
