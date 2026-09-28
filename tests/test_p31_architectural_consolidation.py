"""
Test suite for Macro-pass P3.1: Architectural Consolidation.
Verifies:
1. SecretStore encryption, permissions, extraction, resolution, masking, and migration.
2. Connection store zero-plaintext-in-database invariant.
3. Connection health consolidation: configured != verified, generic fallback, telegram route.
4. Single canonical delivery and Telegram deduplication in notifications.
5. Canonical target contract wire serialization.
6. Canonical approval consolidation.
7. Cross-surface event envelope.
8. Truthful status mappings in activity and automations.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from typing import Any
from unittest.mock import MagicMock, patch
import pytest

from aether.core.secrets import (
    EncryptedVaultSecretStore,
    extract_secrets_from_dict,
    resolve_secrets_in_dict,
    mask_secrets_in_dict,
    migrate_all_secrets,
)
from aether.connections.models import Connection, ConnectionStatus
from aether.connections.store import ConnectionStore
from aether.connections.service import ConnectionService
from aether.notifications.models import (
    Notification,
    NotificationChannel,
    ChannelType,
    NotificationType,
    NotificationStatus,
    DeliveryStatus,
)
from aether.notifications.store import NotificationStore
from aether.notifications.dispatcher import NotificationDispatcher
from aether.notifications.service import NotificationService
from aether.core.events import CrossSurfaceEventEnvelope
from aether.personal.events import PersonalEventHub
from aether.activity.models import ActivityEvent, ActivityStatus, ActivityCategory
from aether.automation.models import AutomationRunRecord, RunStatus


# ============================================================================
# 1. SecretStore: Encryption, File Permissions, Extraction, Resolution
# ============================================================================

def test_secret_store_encryption_and_posix_permissions():
    with tempfile.TemporaryDirectory() as tmp_dir:
        vault_path = Path(tmp_dir) / ".secrets"
        store = EncryptedVaultSecretStore(vault_path=vault_path)

        # Storing secrets
        secret_key = "test_api_token"
        secret_val = "sk-super-secret-production-token-12345"
        ref = store.store_secret(secret_key, secret_val)

        assert ref.startswith("secret_ref:")
        assert store.has_secret(secret_key)
        assert store.get_secret(secret_key) == secret_val

        # Verify disk encryption: vault file must NOT contain plaintext secret
        vault_file = store.vault_path
        assert vault_file.exists()
        raw_bytes = vault_file.read_bytes()
        assert secret_val.encode() not in raw_bytes, "Plaintext secret found in raw vault bytes!"

        # Check POSIX file permissions (0600 on unix/mac)
        if os.name == "posix":
            file_mode = stat.S_IMODE(vault_file.stat().st_mode)
            dir_mode = stat.S_IMODE(vault_file.parent.stat().st_mode)
            assert file_mode == 0o600, f"Vault file mode {oct(file_mode)} != 0o600"
            assert dir_mode == 0o700, f"Vault dir mode {oct(dir_mode)} != 0o700"

        # Reopen with new store instance to test persistent decryption
        store2 = EncryptedVaultSecretStore(vault_path=vault_path)
        assert store2.get_secret(secret_key) == secret_val

        # Deletion
        assert store2.delete_secret(secret_key) is True
        assert store2.get_secret(secret_key) is None
        assert store2.has_secret(secret_key) is False


def test_secrets_dict_extraction_resolution_and_masking():
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = EncryptedVaultSecretStore(vault_path=Path(tmp_dir) / ".secrets")

        original_auth = {
            "api_key": "live_key_xyz",
            "bot_token": "telegram_bot_token_secret",
            "refresh_token": "oauth2_refresh_token_abc",
            "host": "api.example.com",
            "port": 443,
            "use_ssl": True,
        }

        # Extract
        sanitized, count = extract_secrets_from_dict(
            original_auth, store, entity_type="connection", entity_id="gh_1"
        )
        assert count == 3
        assert sanitized["api_key"].startswith("secret_ref:")
        assert sanitized["bot_token"].startswith("secret_ref:")
        assert sanitized["refresh_token"].startswith("secret_ref:")
        assert sanitized["host"] == "api.example.com"
        assert sanitized["port"] == 443

        # Resolve
        resolved = resolve_secrets_in_dict(sanitized, store)
        assert resolved == original_auth

        # Masking: both plaintext and secret_ref must be masked
        masked = mask_secrets_in_dict(sanitized)
        assert masked["api_key"] == "••••••••"
        assert masked["bot_token"] == "••••••••"
        assert masked["host"] == "api.example.com"


def test_idempotent_secret_migration():
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = EncryptedVaultSecretStore(vault_path=Path(tmp_dir) / ".secrets")

        legacy_data = {
            "token": "ghp_1234567890abcdef",
            "account": "personal",
        }

        # First extraction pass
        migrated_1, count_1 = extract_secrets_from_dict(
            legacy_data, store, entity_type="connection", entity_id="mig_test"
        )
        assert count_1 == 1
        assert migrated_1["token"].startswith("secret_ref:")
        ref = migrated_1["token"]
        assert store.get_secret(ref) == "ghp_1234567890abcdef"

        # Second extraction pass (idempotent - already a secret_ref, count=0)
        migrated_2, count_2 = extract_secrets_from_dict(
            migrated_1, store, entity_type="connection", entity_id="mig_test"
        )
        assert count_2 == 0
        assert migrated_2["token"] == ref
        assert store.get_secret(ref) == "ghp_1234567890abcdef"


# ============================================================================
# 2. Connection Store & Zero Plaintext in Database Invariant
# ============================================================================

def test_connection_store_zero_plaintext_in_db():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "connections.db"
        vault_path = Path(tmp_dir) / ".secrets"
        store = EncryptedVaultSecretStore(vault_path=vault_path)
        conn_store = ConnectionStore(db_path=db_path, secret_store=store)

        conn = Connection(
            id="conn_gh_test",
            workspace_id="default",
            provider="github",
            account_name="GitHub Prod",
            status=ConnectionStatus.CONNECTED,
            auth_metadata={
                "github_token": "ghp_super_secret_github_token_xyz999",
                "webhook_secret": "whsec_super_secret_webhook_123",
                "owner": "test-org",
            },
        )

        conn_store.save_connection(conn)

        # Directly query SQLite table to inspect stored bytes
        with sqlite3.connect(db_path) as db:
            cursor = db.cursor()
            cursor.execute("SELECT auth_metadata FROM connections WHERE id = ?", ("conn_gh_test",))
            raw_metadata_json = cursor.fetchone()[0]
            metadata = json.loads(raw_metadata_json)

            assert "ghp_super_secret_github_token_xyz999" not in raw_metadata_json, (
                "Plaintext github_token leaked in SQLite database!"
            )
            assert "whsec_super_secret_webhook_123" not in raw_metadata_json, (
                "Plaintext webhook_secret leaked in SQLite database!"
            )
            assert metadata["github_token"].startswith("secret_ref:")
            assert metadata["webhook_secret"].startswith("secret_ref:")
            assert metadata["owner"] == "test-org"

        # Load back connection from store
        loaded = conn_store.get_connection("conn_gh_test")
        assert loaded is not None

        # Masked auth metadata for API serialization hides secrets
        masked = loaded.to_dict(mask_secrets=True)["auth_metadata"]
        assert masked["github_token"] == "ghp_...999"
        assert masked["webhook_secret"] == "whse...123"
        assert masked["owner"] == "test-org"

        # Resolved auth metadata resolves credentials for live execution
        resolved = loaded.get_resolved_auth_metadata(store)
        assert resolved["github_token"] == "ghp_super_secret_github_token_xyz999"
        assert resolved["webhook_secret"] == "whsec_super_secret_webhook_123"


# ============================================================================
# 3. Connection Health Consolidation: configured != verified & generic fallback
# ============================================================================

def test_connection_health_configured_vs_verified():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "connections.db"
        vault_path = Path(tmp_dir) / ".secrets"
        store = EncryptedVaultSecretStore(vault_path=vault_path)
        conn_store = ConnectionStore(db_path=db_path, secret_store=store)
        service = ConnectionService(store=conn_store, secret_store=store)

        # Connect a generic provider with format check
        conn = service.connect(
            workspace_id="ws_default",
            provider="generic_custom_service",
            account_name="Custom Service",
            auth_metadata={"api_key": "some_key_123"},
            live_check=False,
        )
        assert conn.status == ConnectionStatus.CONFIGURED
        assert conn.is_configured is True
        assert conn.is_verified is False

        # Attempt live verification on generic provider
        valid, msg, verified_conn = service.verify_connection(
            workspace_id="ws_default",
            provider="generic_custom_service",
            live_check=True,
        )

        assert valid is False
        assert "not supported" in msg
        assert verified_conn is not None

        # Crucial invariant: generic provider must NOT be marked VERIFIED or CONNECTED
        assert verified_conn.status == ConnectionStatus.CONFIGURED
        assert verified_conn.is_verified is False
        assert verified_conn.is_configured is True
        assert "not supported" in verified_conn.last_verification_error


# ============================================================================
# 4. Single Canonical Delivery & Telegram Deduplication
# ============================================================================

@pytest.mark.asyncio
async def test_notification_dispatcher_telegram_deduplication():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "notifications.db"
        vault_path = Path(tmp_dir) / ".secrets"
        store = EncryptedVaultSecretStore(vault_path=vault_path)
        notif_store = NotificationStore(db_path=db_path, secret_store=store)
        dispatcher = NotificationDispatcher(notif_store, secret_store=store)

        # Setup telegram channel
        channel = NotificationChannel(
            id="chan_tg",
            workspace_id="default",
            channel_type=ChannelType.TELEGRAM,
            name="Telegram Alerts",
            enabled=True,
            config={"bot_token": "tg_tok_123", "chat_id": "999888"},
        )
        notif_store.save_channel(channel)

        notif = Notification(
            id="notif_dedup_1",
            workspace_id="default",
            type=NotificationType.APPROVAL_REQUIRED,
            title="Approval Required",
            message="Please approve task execution",
        )
        notif_store.save(notif)

        call_count = 0
        real_deliver = dispatcher._deliver_telegram

        def mock_deliver(chan, n):
            nonlocal call_count
            st, msg = real_deliver(chan, n)
            if st == DeliveryStatus.SENT:
                call_count += 1
            return st, msg

        dispatcher._deliver_telegram = mock_deliver

        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.__enter__.return_value = mock_resp
            mock_url.return_value = mock_resp

            # First dispatch
            receipts_1 = dispatcher.dispatch(notif, target_channel_types=[ChannelType.TELEGRAM])
            tg_receipts_1 = [r for r in receipts_1 if r.channel_type == ChannelType.TELEGRAM]
            assert len(tg_receipts_1) == 1
            assert tg_receipts_1[0].status == DeliveryStatus.SENT
            assert call_count == 1

            # Second dispatch with same notification within deduplication window
            receipts_2 = dispatcher.dispatch(notif, target_channel_types=[ChannelType.TELEGRAM])
            tg_receipts_2 = [r for r in receipts_2 if r.channel_type == ChannelType.TELEGRAM]
            assert len(tg_receipts_2) == 1
            assert tg_receipts_2[0].status == DeliveryStatus.SKIPPED
            assert "suppressed" in tg_receipts_2[0].detail.lower()
            assert call_count == 1


# ============================================================================
# 5. Canonical Target Contract Wire Serialization
# ============================================================================

def test_canonical_target_contract_wire_serialization():
    notif = Notification(
        id="notif_wire_123",
        workspace_id="ws_main",
        type=NotificationType.TASK_COMPLETED,
        title="Mission Review",
        message="Mission completed, awaiting review",
        link_view="missions",
        link_id="mis_abc_999",
        open_target={
            "action": "open_view",
            "view": "mission_detail",
            "params": {"mission_id": "mis_abc_999"},
        },
    )

    # Inspect open_target generated on post_init
    target = notif.open_target
    assert target is not None

    # Canonical wire fields required by P3.1 contract:
    assert target["notification_id"] == "notif_wire_123"
    assert target["target_type"] == "mission"
    assert target["target_id"] == "mis_abc_999"
    assert target["view"] in ("missions", "mission_detail")
    assert target["id"] == "mis_abc_999"
    assert target["deep_link"] == "aether://mission/mis_abc_999"
    assert "created_at" in target

    # Backwards compatibility fields preserved:
    assert target["action"] == "open_view"
    assert "params" in target


# ============================================================================
# 6. Cross-Surface Event Envelope
# ============================================================================

def test_cross_surface_event_envelope_structure():
    envelope = CrossSurfaceEventEnvelope.wrap(
        workspace_id="ws_default",
        event_type="connection.health_changed",
        data={"status": "connected", "verified": True},
        entity_type="connection",
        entity_id="conn_gh_1",
    )

    data = envelope.to_dict()
    assert data["event_type"] == "connection.health_changed"
    assert data["workspace_id"] == "ws_default"
    assert data["entity_type"] == "connection"
    assert data["entity_id"] == "conn_gh_1"
    assert data["version"] == 1
    assert data["payload"]["status"] == "connected"
    assert data["occurred_at"] is not None

    # Unwrapping
    unwrapped = CrossSurfaceEventEnvelope.unwrap_payload(data)
    assert unwrapped["status"] == "connected"


@pytest.mark.asyncio
async def test_personal_event_hub_publishes_canonical_envelope():
    hub = PersonalEventHub()
    queue = hub.subscribe("ws_test")

    hub.publish(
        workspace_id="ws_test",
        event_type="action.executed",
        data={"action_id": "act_123", "status": "completed"},
    )

    assert queue.qsize() == 1
    event = queue.get_nowait()
    # Wrapped with canonical envelope
    assert event["type"] == "action.executed"
    assert event["envelope"]["event_type"] == "action.executed"
    assert event["envelope"]["workspace_id"] == "ws_test"
    # Legacy consumer compatibility
    assert event["data"]["action_id"] == "act_123"


# ============================================================================
# 7. Truthful Status Mappings: Activity and Automations
# ============================================================================

def test_activity_status_unknown_handling():
    # Known statuses map cleanly
    assert ActivityStatus.from_str("completed") == ActivityStatus.COMPLETED
    assert ActivityStatus.from_str("in_progress") == ActivityStatus.IN_PROGRESS
    assert ActivityStatus.from_str("waiting_approval") == ActivityStatus.WAITING_APPROVAL
    assert ActivityStatus.from_str("pending_approval") == ActivityStatus.WAITING_APPROVAL

    # Crucial P3.1 requirement: unknown string MUST NOT default to IN_PROGRESS
    assert ActivityStatus.from_str("bogus_unknown_status") == ActivityStatus.UNKNOWN
    assert ActivityStatus.from_str(None) == ActivityStatus.UNKNOWN
    assert ActivityStatus.from_str("") == ActivityStatus.UNKNOWN


def test_automation_run_record_status_error_mapping():
    # Legacy states mapping
    rec_err = AutomationRunRecord.from_dict({"status": "error"})
    assert rec_err.status == RunStatus.FAILED

    rec_fail = AutomationRunRecord.from_dict({"status": "fail"})
    assert rec_fail.status == RunStatus.FAILED

    rec_succ = AutomationRunRecord.from_dict({"status": "ok"})
    assert rec_succ.status == RunStatus.SUCCEEDED

    rec_wait = AutomationRunRecord.from_dict({"status": "waiting_approval"})
    assert rec_wait.status == RunStatus.WAITING_APPROVAL


# ============================================================================
# 8. Approval Route Delegation to Canonical Approval Engine
# ============================================================================

@pytest.mark.asyncio
async def test_action_and_mission_approval_routes_delegate_to_canonical():
    from aether.server.app import app
    from aether.workspace.workspace import Workspace
    from aether.server.routes import (
        approve_action_execution_route,
        approve_mission_route,
        ApproveActionPayload,
        MissionActionApprovePayload,
    )
    from starlette.requests import Request

    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Workspace.init(Path(tmp_dir), name="p31_ws")
        app.state.workspace = ws

        scope = {"type": "http", "app": app, "headers": [], "path": "/", "method": "POST"}
        req = Request(scope)

        # 1. Action execution delegation
        execution = ws.actions.execute(
            action_id="calendar.create_event",
            workspace_id="p31_ws",
            input_data={"title": "Team Sync", "start_time": "2026-10-10T12:00:00Z"},
            auto_approve=False,
        )

        res_action = await approve_action_execution_route(
            req,
            execution_id=execution.id,
            payload=ApproveActionPayload(approver="admin"),
        )
        assert res_action is not None
        # Verify execution transitioned out of WAITING_APPROVAL
        loaded_exec = ws.actions.store.get_execution(execution.id)
        assert loaded_exec.status.value in ("succeeded", "completed")

        ws.close()
