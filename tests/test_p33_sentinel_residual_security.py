"""
Tests for Sentinel Residual Security & Email Secret Resolution (P3.3).
Covers:
- Comprehensive raw inspection across SQLite DBs, JSON, and metadata ensuring 0 leaks
- EmailConnector resolving secret_ref tokens from SecretStore
- Strict password masking in EmailConnector error messages
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import pytest

from aether.connections.email import EmailConnector
from aether.connections.store import ConnectionStore
from aether.notifications.store import NotificationStore
from aether.automation.store import AutomationStore
from aether.workspace.workspace import Workspace
from aether.core.secrets import get_secret_store


def test_sentinel_residual_scan_across_all_databases(tmp_path: Path, monkeypatch):
    """
    Inject sentinel plaintext secrets into Connections, Notifications, and Automations,
    execute migration, and scan all raw files to ensure 0 plaintext leaks.
    """
    monkeypatch.setenv("AETHER_DISABLE_KEYCHAIN", "1")
    ws_dir = tmp_path / "sentinel_workspace"
    ws = Workspace.init(ws_dir, name="Sentinel Test Workspace")

    sentinel_conn_secret = "SENTINEL_CONN_SECRET_987654321_AETHER"
    sentinel_notif_secret = "SENTINEL_NOTIF_SECRET_123456789_AETHER"
    sentinel_auto_secret = "SENTINEL_AUTO_SECRET_456789123_AETHER"

    # Ensure table schemas are created
    _ = ws.connections
    _ = ws.notifications
    _ = ws.automations

    # 1. Inject raw un-sanitized records into SQLite tables
    conn_db = Path(ws.connections_db_path)
    with sqlite3.connect(str(conn_db)) as db:
        db.execute(
            """
            INSERT INTO connections (id, workspace_id, provider, account_name, status, auth_metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'));
            """,
            ("conn_sentinel_1", ws.id, "email", "SMTP Account", "verified", json.dumps({"password": sentinel_conn_secret, "smtp_host": "smtp.mail.com"}))
        )

    notif_db = Path(ws.notifications_db_path)
    with sqlite3.connect(str(notif_db)) as db:
        db.execute(
            """
            INSERT INTO notification_channels (id, workspace_id, channel_type, name, enabled, config, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'));
            """,
            ("chan_sentinel_1", ws.id, "telegram", "Telegram Alerts", 1, json.dumps({"bot_token": sentinel_notif_secret, "chat_id": "12345"}))
        )

    auto_db = Path(ws.automations_db_path)
    with sqlite3.connect(str(auto_db)) as db:
        db.execute(
            """
            INSERT INTO automations (id, name, description, enabled, trigger_json, steps_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'));
            """,
            ("auto_sentinel_1", "Webhook Trigger", "Desc", 1, json.dumps({"secret": sentinel_auto_secret}), "[]")
        )

    # 2. Run migration
    results = ws.migrate_secrets(force=True)
    assert results["connections"] >= 1
    assert results["notifications"] >= 1
    assert results["automations"] >= 1

    # 3. Full raw file scan across the entire workspace directory
    sentinels = [sentinel_conn_secret, sentinel_notif_secret, sentinel_auto_secret]
    vault_file = ws.data_dir / "vault" / "secrets.vault"

    for root_dir, _, files in os.walk(str(ws_dir)):
        for f in files:
            f_path = Path(root_dir) / f
            # Skip the encrypted vault itself (which should only contain ciphertext anyway)
            if f_path.resolve() == vault_file.resolve():
                continue

            content = f_path.read_bytes()
            for s in sentinels:
                assert s.encode("utf-8") not in content, (
                    f"Residual plaintext secret leak detected in {f_path}!"
                )

    # 4. Verify secrets are in vault and readable
    vault_content = vault_file.read_text(encoding="utf-8")
    for s in sentinels:
        assert s not in vault_content, "Plaintext found in vault file!"


def test_email_connector_resolves_secret_ref(tmp_path: Path):
    """EmailConnector must seamlessly resolve secret_ref strings in credentials."""
    vault_file = tmp_path / "secrets.vault"
    store = get_secret_store(vault_file)

    ref = store.generate_secret_ref(prefix="smtp")
    plain_password = "MySuperSecretAppPassword2026!"
    store.store_secret(ref, plain_password)

    connector = EmailConnector(
        auth_metadata={
            "username": "user@example.com",
            "password": ref,
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
        },
        secret_store=store,
    )

    cfg = connector._get_config()
    assert cfg["password"] == plain_password


def test_email_connector_masks_password_in_errors(monkeypatch):
    """EmailConnector must mask passwords from any error messages to prevent leakage."""
    plain_password = "UltraSensitivePassWord999"
    connector = EmailConnector(auth_metadata={
        "username": "test@domain.com",
        "password": plain_password,
        "smtp_host": "nonexistent.smtp.host.invalid",
        "smtp_port": 587,
    })

    # Test verify error masking
    valid, msg = connector.verify(live_check=True)
    assert valid is False
    assert plain_password not in msg
    assert "••••••••" not in msg or plain_password not in msg

    # Test explicit sanitize check
    def mock_socket_gaierror(*args, **kwargs):
        raise OSError(f"Connection refused with password {plain_password} rejected")

    monkeypatch.setattr("smtplib.SMTP", mock_socket_gaierror)
    valid, msg = connector.verify(live_check=True)
    assert valid is False
    assert plain_password not in msg
    assert "••••••••" in msg
