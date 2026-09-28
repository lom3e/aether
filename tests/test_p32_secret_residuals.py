"""
Tests for Secret Residual Scanner (P3.2).
Injects sentinel secret tokens across connections, notifications, and automations,
and verifies through forensic scans that zero plaintext secrets leak into:
- SQLite database tables
- Disk workspace files / JSON
- External API responses (model serializations)
- Exception messages / logs
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sqlite3
import pytest

from aether.workspace.workspace import Workspace
from aether.connections.models import Connection, ConnectionStatus
from aether.notifications.models import NotificationChannel, ChannelType
from aether.automation.models import AutomationDefinition, TriggerConfig, TriggerType, PipelineStep
from aether.core.secrets import (
    EncryptedVaultSecretStore,
    migrate_all_secrets,
    mask_secrets_deep,
)

SENTINELS = {
    "github_token": "SENTINEL_GH_PAT_SECRET_XYZ9876543210",
    "smtp_password": "SENTINEL_SMTP_PASS_ULTRA_CONFIDENTIAL_12345",
    "webhook_secret": "SENTINEL_WEBHOOK_SECRET_HIGH_ENTROPY_45678",
    "google_refresh": "SENTINEL_GOOGLE_REFRESH_RESTRICTED_TOKEN_11111",
}


def test_sentinel_residual_scan_across_databases_and_disk(tmp_path: Path, caplog):
    """
    Configure multiple integrations with unique sentinel secrets, run migration,
    and scan all SQLite databases, JSON files, logs, and dictionaries on disk.
    Plaintext sentinels MUST ONLY exist inside the encrypted vault file!
    """
    ws_dir = tmp_path / "ws_sentinels"
    ws = Workspace.get_or_init(ws_dir, "Sentinel WS")
    vault_file = ws.data_dir / "vault" / "secrets.vault"
    store = EncryptedVaultSecretStore(vault_file)

    with caplog.at_level(logging.DEBUG):
        # 1. Add connection with Google Calendar & GitHub tokens
        conn = Connection(
            id="conn-google-1",
            workspace_id=ws.name,
            provider="google_calendar",
            account_name="Work Calendar",
            status=ConnectionStatus.CONFIGURED,
            auth_metadata={
                "client_id": "public-client.apps.googleusercontent.com",
                "client_secret": "SENTINEL_GOOGLE_CLIENT_SECRET_9999",
                "refresh_token": SENTINELS["google_refresh"],
            },
        )
        ws.connections.store.save_connection(conn)

        # 2. Add SMTP email channel
        chan = NotificationChannel(
            id="chan-email-1",
            workspace_id=ws.name,
            channel_type=ChannelType.EMAIL,
            name="SMTP Alerts",
            enabled=True,
            config={
                "smtp_host": "smtp.mailgun.org",
                "smtp_user": "postmaster@mailgun.org",
                "smtp_pass": SENTINELS["smtp_password"],
            },
        )
        ws.notifications.store.save_channel(chan)

        # 3. Add webhook automation
        auto = AutomationDefinition(
            id="auto-sentinel-1",
            name="Deploy Webhook",
            enabled=True,
            trigger=TriggerConfig(
                type=TriggerType.WEBHOOK,
                webhook_slug="deploy-webhook",
                webhook_secret=SENTINELS["webhook_secret"],
                github_token=SENTINELS["github_token"],
            ),
            steps=[PipelineStep(id="step1", name="Run deploy")],
        )
        ws.automations.save_automation(auto)

        # Execute migration
        migrate_all_secrets(ws, secret_store=store)

    # =========================================================================
    # FORENSIC AUDIT SCAN
    # =========================================================================

    all_sentinels = list(SENTINELS.values()) + ["SENTINEL_GOOGLE_CLIENT_SECRET_9999"]

    # 1. Scan SQLite files across workspace data dir
    sqlite_files = list(ws.data_dir.rglob("*.db"))
    assert len(sqlite_files) > 0, "Expected SQLite database files in data_dir"

    for db_path in sqlite_files:
        raw_db_bytes = db_path.read_bytes()
        for sentinel in all_sentinels:
            assert sentinel.encode("utf-8") not in raw_db_bytes, (
                f"LEAK DETECTED: Plaintext sentinel '{sentinel}' found in raw SQLite file {db_path.name}"
            )

        # Also inspect table contents via SQL queries
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
            for tbl in tables:
                rows = cursor.execute(f"SELECT * FROM {tbl};").fetchall()
                table_dump = json.dumps([list(row) for row in rows], default=str)
                for sentinel in all_sentinels:
                    assert sentinel not in table_dump, (
                        f"LEAK DETECTED: Plaintext sentinel '{sentinel}' found in table '{tbl}' of {db_path.name}"
                    )

    # 2. Scan all JSON and text files in workspace (EXCEPT secrets.vault itself!)
    for text_file in ws.data_dir.rglob("*"):
        if text_file.is_file() and text_file.resolve() != vault_file.resolve():
            file_content = text_file.read_text(errors="ignore")
            for sentinel in all_sentinels:
                assert sentinel not in file_content, (
                    f"LEAK DETECTED: Plaintext sentinel '{sentinel}' found in file {text_file}"
                )

    # 3. Verify external API serialization masking
    # A connection's to_dict() must not leak plaintext secrets
    retrieved_conn = ws.connections.store.get_connection("conn-google-1")
    assert retrieved_conn is not None
    conn_dict = retrieved_conn.to_dict()
    for sentinel in all_sentinels:
        assert sentinel not in json.dumps(conn_dict), (
            f"LEAK DETECTED: Plaintext sentinel '{sentinel}' found in Connection.to_dict() serialization"
        )

    # 4. Verify log records do not contain sentinels
    log_text = caplog.text
    for sentinel in all_sentinels:
        assert sentinel not in log_text, (
            f"LEAK DETECTED: Plaintext sentinel '{sentinel}' found in application log output"
        )
