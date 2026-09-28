"""
P3.2 Release-Grade Hardening: Provider Test Harness (Live & Mock).
Enforces:
1. live_provider: Explicit skip/fail on missing real credentials (NO fake passes).
2. mock_provider: Complete deterministic wire-level verification of all 7 providers:
   - GitHub
   - Google Calendar
   - SMTP Email
   - Slack
   - Telegram
   - Notion
   - OpenAPI
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from aether.connections.github import GitHubConnector
from aether.connections.google_calendar import GoogleCalendarConnector
from aether.connections.email import EmailConnector
from aether.connections.slack import SlackConnector
from aether.connections.telegram import TelegramConnector
from aether.connections.notion import NotionConnector
from aether.connections.openapi import OpenAPIConnector
from aether.connections.models import ConnectionStatus
from aether.connections.service import ConnectionService
from aether.connections.store import ConnectionStore
from aether.core.secrets import EncryptedVaultSecretStore


@pytest.fixture
def service_setup(tmp_path: Path):
    vault_file = tmp_path / "secrets.vault"
    store = EncryptedVaultSecretStore(vault_file)
    db_path = tmp_path / "connections.db"
    conn_store = ConnectionStore(str(db_path), secret_store=store)
    service = ConnectionService(store=conn_store, secret_store=store)
    return service, conn_store, store


# =============================================================================
# A. LIVE PROVIDER TESTS (Require explicit real credentials, skips otherwise)
# =============================================================================

@pytest.mark.live_provider
def test_live_github_provider(service_setup):
    service, _, _ = service_setup
    token = os.environ.get("AETHER_LIVE_GITHUB_TOKEN")
    if not token:
        pytest.skip("Live GitHub test skipped: AETHER_LIVE_GITHUB_TOKEN is not configured")

    connector = GitHubConnector(auth_metadata={"token": token})
    valid, msg = connector.verify(live_check=True)
    assert valid, f"Live GitHub verification failed: {msg}"


@pytest.mark.live_provider
def test_live_google_calendar_provider(service_setup):
    service, _, _ = service_setup
    client_id = os.environ.get("AETHER_LIVE_GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("AETHER_LIVE_GOOGLE_CLIENT_SECRET")
    refresh_token = os.environ.get("AETHER_LIVE_GOOGLE_REFRESH_TOKEN")

    if not (client_id and client_secret and refresh_token):
        pytest.skip(
            "Live Google Calendar test skipped: AETHER_LIVE_GOOGLE_CLIENT_ID/SECRET/REFRESH_TOKEN not set"
        )

    connector = GoogleCalendarConnector(
        auth_metadata={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }
    )
    valid, msg = connector.verify(live_check=True)
    assert valid, f"Live Google Calendar verification failed: {msg}"


@pytest.mark.live_provider
def test_live_smtp_provider(service_setup):
    service, _, _ = service_setup
    host = os.environ.get("AETHER_LIVE_SMTP_HOST")
    user = os.environ.get("AETHER_LIVE_SMTP_USER")
    password = os.environ.get("AETHER_LIVE_SMTP_PASS")

    if not (host and user and password):
        pytest.skip("Live SMTP test skipped: AETHER_LIVE_SMTP_HOST/USER/PASS not set")

    connector = EmailConnector(
        auth_metadata={
            "smtp_host": host,
            "username": user,
            "password": password,
        }
    )
    valid, msg = connector.verify(live_check=True)
    assert valid, f"Live SMTP verification failed: {msg}"


@pytest.mark.live_provider
def test_live_slack_provider(service_setup):
    service, _, _ = service_setup
    bot_token = os.environ.get("AETHER_LIVE_SLACK_BOT_TOKEN")
    if not bot_token:
        pytest.skip("Live Slack test skipped: AETHER_LIVE_SLACK_BOT_TOKEN not set")

    connector = SlackConnector(auth_metadata={"bot_token": bot_token})
    valid, msg = connector.verify(live_check=True)
    assert valid, f"Live Slack verification failed: {msg}"


@pytest.mark.live_provider
def test_live_telegram_provider(service_setup):
    service, _, _ = service_setup
    bot_token = os.environ.get("AETHER_LIVE_TELEGRAM_BOT_TOKEN")
    if not bot_token:
        pytest.skip("Live Telegram test skipped: AETHER_LIVE_TELEGRAM_BOT_TOKEN not set")

    connector = TelegramConnector(auth_metadata={"bot_token": bot_token})
    valid, msg = connector.verify(live_check=True)
    assert valid, f"Live Telegram verification failed: {msg}"


@pytest.mark.live_provider
def test_live_notion_provider(service_setup):
    service, _, _ = service_setup
    api_key = os.environ.get("AETHER_LIVE_NOTION_KEY")
    if not api_key:
        pytest.skip("Live Notion test skipped: AETHER_LIVE_NOTION_KEY not set")

    connector = NotionConnector(auth_metadata={"token": api_key})
    valid, msg = connector.verify(live_check=True)
    assert valid, f"Live Notion verification failed: {msg}"


@pytest.mark.live_provider
def test_live_openapi_provider(service_setup):
    service, _, _ = service_setup
    spec_url = os.environ.get("AETHER_LIVE_OPENAPI_SPEC_URL")
    if not spec_url:
        pytest.skip("Live OpenAPI test skipped: AETHER_LIVE_OPENAPI_SPEC_URL not set")

    connector = OpenAPIConnector(auth_metadata={"spec_url": spec_url})
    valid, msg = connector.verify(live_check=True)
    assert valid, f"Live OpenAPI verification failed: {msg}"


# =============================================================================
# B. MOCK PROVIDER VERIFICATION TESTS (Deterministic contract validation)
# =============================================================================

@pytest.mark.mock_provider
def test_mock_github_verification():
    connector = GitHubConnector(auth_metadata={"token": "ghp_test_mock_token_12345"})
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {"x-oauth-scopes": "repo, user"}
        mock_resp.read.return_value = json.dumps({"login": "octocat"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        valid, msg = connector.verify(live_check=True)
        assert valid
        assert "octocat" in msg or "verified" in msg.lower()


@pytest.mark.mock_provider
def test_mock_google_calendar_verification():
    connector = GoogleCalendarConnector(
        auth_metadata={
            "client_id": "mock-client-id.apps.googleusercontent.com",
            "client_secret": "mock-client-secret",
            "refresh_token": "mock-refresh-token",
            "access_token": "ya29.mock_token_12345",
        }
    )
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_cal_resp = MagicMock()
        mock_cal_resp.status = 200
        mock_cal_resp.read.return_value = json.dumps({"items": [{"id": "primary"}]}).encode("utf-8")
        mock_cal_resp.__enter__.return_value = mock_cal_resp
        mock_urlopen.return_value = mock_cal_resp

        valid, msg = connector.verify(live_check=True)
        assert valid
        assert "verified" in msg.lower() or "success" in msg.lower() or "active" in msg.lower()


@pytest.mark.mock_provider
def test_mock_smtp_verification():
    connector = EmailConnector(
        auth_metadata={
            "smtp_host": "smtp.mailgun.org",
            "smtp_port": 587,
            "username": "postmaster@mailgun.org",
            "password": "mock_secret_password",
        }
    )
    with patch("smtplib.SMTP") as mock_smtp:
        inst = MagicMock()
        mock_smtp.return_value = inst
        inst.__enter__.return_value = inst

        valid, msg = connector.verify(live_check=True)
        assert valid
        assert "verified" in msg.lower() or "connected" in msg.lower()
        inst.login.assert_called_once_with("postmaster@mailgun.org", "mock_secret_password")


@pytest.mark.mock_provider
def test_mock_slack_verification():
    connector = SlackConnector(auth_metadata={"bot_token": "xoxb-mock-token-12345"})
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"ok": True, "bot_id": "B12345", "user": "aether_bot"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        valid, msg = connector.verify(live_check=True)
        assert valid
        assert "verified" in msg.lower() or "aether_bot" in msg


@pytest.mark.mock_provider
def test_mock_telegram_verification():
    connector = TelegramConnector(auth_metadata={"bot_token": "1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ123456789"})
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"ok": True, "result": {"username": "aether_assistant_bot"}}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        valid, msg = connector.verify(live_check=True)
        assert valid
        assert "verified" in msg.lower() or "aether_assistant_bot" in msg


@pytest.mark.mock_provider
def test_mock_notion_verification():
    connector = NotionConnector(auth_metadata={"token": "secret_mock_notion_key_12345"})
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"type": "bot", "bot": {"owner": {"type": "user"}}}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        valid, msg = connector.verify(live_check=True)
        assert valid
        assert "verified" in msg.lower() or "bot" in msg.lower()


@pytest.mark.mock_provider
def test_mock_openapi_verification():
    sample_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Petstore API", "version": "1.0.0"},
        "paths": {
            "/pets": {
                "get": {
                    "operationId": "listPets",
                    "responses": {"200": {"description": "List of pets"}},
                }
            }
        },
    }
    connector = OpenAPIConnector(auth_metadata={"spec_content": json.dumps(sample_spec)})
    valid, msg = connector.verify(live_check=True)
    assert valid
    assert "petstore api" in msg.lower() or "verified" in msg.lower() or "listPets" in str(connector.capabilities)
