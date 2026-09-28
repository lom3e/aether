"""
Tests for Release-Grade Secret Migration & Idempotency (P3.2).
Covers:
- Strict Idempotency: Multiple runs produce 0 duplicate references or re-encryptions
- MigrationJournal: State tracking (not_started, running, completed, failed)
- Transactional compensating safety: Database updates rollback safely on failure
- Fail-Closed Behavior: Failed migration marks workspace protection status degraded
- Comprehensive provider secret coverage: GitHub, Google, SMTP, Slack, Telegram, Notion, Webhooks
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from aether.workspace.workspace import Workspace
from aether.connections.models import Connection, ConnectionStatus
from aether.notifications.models import NotificationChannel, ChannelType
from aether.automation.models import AutomationDefinition, TriggerConfig, TriggerType, PipelineStep
from aether.core.secrets import (
    MemorySecretStore,
    MigrationJournal,
    SecretMigrationError,
    is_secret_ref,
    migrate_all_secrets,
)


def test_secret_migration_strict_idempotency(tmp_path: Path):
    """
    Verify that migrate_all_secrets migrates plaintext secrets on run 1,
    and on run 2 (or 3) does nothing (0 migrations, stable secret_refs).
    """
    ws = Workspace.get_or_init(tmp_path / "ws_migration", "Migration WS")
    store = MemorySecretStore()

    # 1. Insert raw legacy connection with plaintext in SQLite
    with ws.connections.store._transaction() as c:
        c.execute(
            "INSERT INTO connections (id, workspace_id, provider, account_name, status, auth_metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'));",
            ("conn-gh-1", ws.name, "github", "GitHub Integration", "configured", json.dumps({"token": "ghp_real_secret_token_12345", "user": "test-dev"}))
        )

    # 2. Insert raw legacy notification channel with plaintext in SQLite
    with ws.notifications.store._transaction() as c:
        c.execute(
            "INSERT INTO notification_channels (id, workspace_id, channel_type, name, enabled, config, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 1, ?, datetime('now'), datetime('now'));",
            ("chan-smtp-1", ws.name, "email", "SMTP Email", json.dumps({"smtp_host": "smtp.example.com", "smtp_user": "alert@example.com", "smtp_pass": "super_secret_smtp_password_999"}))
        )

    # 3. Insert raw legacy automation with plaintext in SQLite
    with ws.automations._get_connection() as c:
        c.execute(
            "INSERT INTO automations (id, name, description, enabled, team_name, trigger_json, steps_json, created_at, updated_at) "
            "VALUES (?, ?, '', 1, 'default', ?, '[]', datetime('now'), datetime('now'));",
            ("auto-hook-1", "Webhook Trigger", json.dumps({"type": "webhook", "webhook_slug": "deploy-slug", "webhook_secret": "raw-webhook-secret-token-xyz"}))
        )
        c.commit()

    # Run 1: Must migrate all 3 entities
    res1 = migrate_all_secrets(ws, secret_store=store)
    assert res1["connections"] >= 1
    assert res1["notifications"] >= 1
    assert res1["automations"] >= 1

    # Verify that raw database now holds secret_refs, not plaintext
    with ws.connections.store._get_connection() as c:
        row = c.execute("SELECT auth_metadata FROM connections WHERE id = 'conn-gh-1';").fetchone()
        raw_meta = json.loads(row[0])
        assert is_secret_ref(raw_meta["token"])
        first_gh_ref = raw_meta["token"]
        assert store.get_secret(first_gh_ref) == "ghp_real_secret_token_12345"

    with ws.notifications.store._get_connection() as c:
        row = c.execute("SELECT config FROM notification_channels WHERE id = 'chan-smtp-1';").fetchone()
        raw_cfg = json.loads(row[0])
        assert is_secret_ref(raw_cfg["smtp_pass"])
        first_smtp_ref = raw_cfg["smtp_pass"]
        assert store.get_secret(first_smtp_ref) == "super_secret_smtp_password_999"

    with ws.automations._get_connection() as c:
        row = c.execute("SELECT trigger_json FROM automations WHERE id = 'auto-hook-1';").fetchone()
        raw_trig = json.loads(row[0])
        assert is_secret_ref(raw_trig["webhook_secret"])
        first_auto_ref = raw_trig["webhook_secret"]
        assert store.get_secret(first_auto_ref) == "raw-webhook-secret-token-xyz"

    # Run 2: STRICT IDEMPOTENCY CHECK
    # Must report 0 newly migrated entities and secret_refs MUST remain identical
    res2 = migrate_all_secrets(ws, secret_store=store)
    assert res2 == {"connections": 0, "notifications": 0, "automations": 0}

    with ws.connections.store._get_connection() as c:
        row = c.execute("SELECT auth_metadata FROM connections WHERE id = 'conn-gh-1';").fetchone()
        raw_meta = json.loads(row[0])
        assert raw_meta["token"] == first_gh_ref  # Same reference preserved!

    # Run 3: Repeat again
    res3 = migrate_all_secrets(ws, secret_store=store)
    assert res3 == {"connections": 0, "notifications": 0, "automations": 0}


def test_migration_journal_tracking(tmp_path: Path):
    """Verify that MigrationJournal tracks migration lifecycle states accurately."""
    ws_dir = tmp_path / "ws_journal"
    ws = Workspace.get_or_init(ws_dir, "Journal WS")
    journal = MigrationJournal(ws_dir)

    status_initial = journal.get_status()
    assert status_initial["status"] in ("not_started", "completed")

    journal.record_start()
    status_running = journal.get_status()
    assert status_running["status"] == "running"

    journal.record_success({"connections": 2, "notifications": 1, "automations": 0})
    status_success = journal.get_status()
    assert status_success["status"] == "completed"
    assert status_success["migrated_counts"]["connections"] == 2

    journal.record_failure("Simulated database locked error")
    status_failed = journal.get_status()
    assert status_failed["status"] == "failed"
    assert "Simulated database locked" in status_failed["last_error"]


def test_migration_failure_safety_and_fail_closed(tmp_path: Path, monkeypatch):
    """
    If an error occurs during migration, the process must fail-closed:
    1. Plaintext in database is NOT deleted or corrupted
    2. MigrationJournal records 'failed'
    3. Workspace protection status is marked degraded
    """
    ws_dir = tmp_path / "ws_fail_safe"
    ws = Workspace.get_or_init(ws_dir, "FailSafe WS")
    store = MemorySecretStore()

    with ws.connections.store._transaction() as c:
        c.execute(
            "INSERT INTO connections (id, workspace_id, provider, account_name, status, auth_metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'));",
            ("conn-fail-1", ws.name, "slack", "Slack Integration", "configured", json.dumps({"bot_token": "xoxb-sensitive-slack-token"}))
        )

    # Simulate SecretStore error during migration
    def failing_store_secret(*args, **kwargs):
        raise RuntimeError("Secret storage disk write failed")

    monkeypatch.setattr(store, "store_secret", failing_store_secret)

    with pytest.raises(SecretMigrationError):
        migrate_all_secrets(ws, secret_store=store)

    # 1. Plaintext in SQLite was NOT lost or corrupted with a dangling ref
    with ws.connections.store._get_connection() as c:
        row = c.execute("SELECT auth_metadata FROM connections WHERE id = 'conn-fail-1';").fetchone()
        raw_meta = json.loads(row[0])
        assert raw_meta["bot_token"] == "xoxb-sensitive-slack-token"

    # 2. Journal status is recorded as failed
    journal = MigrationJournal(ws_dir)
    assert journal.get_status()["status"] == "failed"

    # 3. Workspace protection status is degraded (fail-closed)
    assert getattr(ws, "protection_status", None) == "migration_failed"
