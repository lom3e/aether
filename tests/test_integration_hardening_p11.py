"""
Tests for Macro-pass P1.1: Integration Hardening.
Verifies all connectors, truthfulness of statuses, error handling,
security defaults (e.g. Telegram whitelist), and secret masking.
"""

import json
import socket
import ssl
import smtplib
import pytest
from unittest.mock import MagicMock, patch

from aether.connections.models import ConnectionStatus
from aether.connections.store import ConnectionStore
from aether.connections.github import GitHubConnector
from aether.connections.email import EmailConnector
from aether.connections.slack import SlackConnector
from aether.connections.telegram import TelegramConnector
from aether.connections.http import HTTPConnector
from aether.connections.notion import NotionConnector
from aether.connections.openapi import OpenAPIConnector
from aether.connections.service import ConnectionService
from aether.github.models import GitHubRateLimitError, GitHubAuthError


# ============================================================================
# 1. GITHUB HARDENING TESTS
# ============================================================================

def test_github_format_validation():
    conn = GitHubConnector()
    # Missing token
    valid, msg = conn.verify({}, live_check=False)
    assert not valid
    assert "token" in msg.lower()

    # Empty token
    valid, msg = conn.verify({"token": "   "}, live_check=False)
    assert not valid

    # Present token
    valid, msg = conn.verify({"token": "ghp_validtesttoken1234567890"}, live_check=False)
    assert valid


def test_github_live_check_success():
    conn = GitHubConnector()
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"login": "testuser", "type": "User"}).encode("utf-8")
        mock_url.return_value.__enter__.return_value = mock_resp

        valid, msg = conn.verify({"token": "ghp_valid"}, live_check=True)
        assert valid
        assert "testuser" in msg


def test_github_live_check_auth_failure():
    import urllib.error
    conn = GitHubConnector()
    with patch("urllib.request.urlopen") as mock_url:
        mock_err = urllib.error.HTTPError("https://api.github.com/user", 401, "Unauthorized", {}, None)
        mock_err.read = MagicMock(return_value=b'{"message": "Bad credentials"}')
        mock_url.side_effect = mock_err

        valid, msg = conn.verify({"token": "ghp_badtoken"}, live_check=True)
        assert not valid
        assert "authentication failed" in msg.lower() or "bad credentials" in msg.lower()


def test_github_live_check_rate_limit_429():
    import urllib.error
    conn = GitHubConnector()
    with patch("urllib.request.urlopen") as mock_url:
        mock_err = urllib.error.HTTPError("https://api.github.com/user", 429, "Too Many Requests", {}, None)
        mock_err.read = MagicMock(return_value=b'{"message": "Rate limit exceeded"}')
        mock_url.side_effect = mock_err

        valid, msg = conn.verify({"token": "ghp_limited"}, live_check=True)
        assert not valid
        assert "rate limit" in msg.lower()


def test_github_live_check_rate_limit_403_remaining_zero():
    import urllib.error
    from email.message import Message
    conn = GitHubConnector()
    with patch("urllib.request.urlopen") as mock_url:
        headers = Message()
        headers["x-ratelimit-remaining"] = "0"
        headers["x-ratelimit-reset"] = "1700000000"
        mock_err = urllib.error.HTTPError("https://api.github.com/user", 403, "Forbidden", headers, None)
        mock_err.read = MagicMock(return_value=b'{"message": "API rate limit exceeded for user"}')
        mock_url.side_effect = mock_err

        valid, msg = conn.verify({"token": "ghp_limited"}, live_check=True)
        assert not valid
        assert "rate limit" in msg.lower()


# ============================================================================
# 2. EMAIL / SMTP HARDENING TESTS
# ============================================================================

def test_email_format_validation():
    conn = EmailConnector()
    # Missing fields
    valid, msg = conn.verify({}, live_check=False)
    assert not valid
    assert "required" in msg.lower() or "missing" in msg.lower()

    # Valid format
    valid, msg = conn.verify({
        "username": "user@example.com",
        "password": "apppassword",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587
    }, live_check=False)
    assert valid


def test_email_dns_failure():
    conn = EmailConnector()
    creds = {
        "username": "user@example.com",
        "password": "secretpassword",
        "smtp_host": "nonexistent.domain.xyz12345",
        "smtp_port": 587
    }
    with patch("smtplib.SMTP", side_effect=socket.gaierror("Name or service not known")):
        valid, msg = conn.verify(creds, live_check=True)
        assert not valid
        assert "dns" in msg.lower() or "resolve" in msg.lower()


def test_email_timeout_failure():
    conn = EmailConnector()
    creds = {
        "username": "user@example.com",
        "password": "secretpassword",
        "smtp_host": "smtp.slow.com",
        "smtp_port": 587
    }
    with patch("smtplib.SMTP", side_effect=socket.timeout("Timed out")):
        valid, msg = conn.verify(creds, live_check=True)
        assert not valid
        assert "timed out" in msg.lower()


def test_email_tls_failure():
    conn = EmailConnector()
    creds = {
        "username": "user@example.com",
        "password": "secretpassword",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "use_tls": True
    }
    mock_smtp = MagicMock()
    mock_smtp.starttls.side_effect = ssl.SSLError("CERTIFICATE_VERIFY_FAILED")
    with patch("smtplib.SMTP", return_value=mock_smtp):
        valid, msg = conn.verify(creds, live_check=True)
        assert not valid
        assert "tls" in msg.lower() or "ssl" in msg.lower()


def test_email_auth_failure():
    conn = EmailConnector()
    creds = {
        "username": "user@example.com",
        "password": "badpassword",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587
    }
    mock_smtp = MagicMock()
    mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication failed")
    with patch("smtplib.SMTP", return_value=mock_smtp):
        valid, msg = conn.verify(creds, live_check=True)
        assert not valid
        assert "authentication failed" in msg.lower()


def test_email_live_check_success_ssl_and_test_recipient():
    conn = EmailConnector()
    creds = {
        "username": "user@example.com",
        "password": "goodpassword",
        "smtp_host": "smtp.example.com",
        "smtp_port": 465,
        "use_ssl": True,
        "test_recipient": "dest@example.com"
    }
    mock_smtp_ssl = MagicMock()
    with patch("smtplib.SMTP_SSL", return_value=mock_smtp_ssl) as mock_class:
        valid, msg = conn.verify(creds, live_check=True)
        assert valid
        mock_class.assert_called_once()
        mock_smtp_ssl.login.assert_called_with("user@example.com", "goodpassword")
        mock_smtp_ssl.send_message.assert_called_once()


# ============================================================================
# 3. SLACK HARDENING TESTS
# ============================================================================

def test_slack_format_validation():
    conn = SlackConnector()
    # Neither token nor webhook
    valid, msg = conn.verify({}, live_check=False)
    assert not valid
    assert "token" in msg.lower() or "webhook" in msg.lower()

    # Bad token prefix
    valid, msg = conn.verify({"bot_token": "random_string"}, live_check=False)
    assert not valid
    assert "prefix" in msg.lower() or "format" in msg.lower()

    # Valid token prefix
    valid, msg = conn.verify({"bot_token": "xoxb-12345-67890-abcdef"}, live_check=False)
    assert valid


def test_slack_live_check_success():
    conn = SlackConnector()
    creds = {"bot_token": "xoxb-valid-bot-token"}
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({
        "ok": True,
        "user": "aether_bot",
        "team": "Aether Space"
    }).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = mock_resp
        valid, msg = conn.verify(creds, live_check=True)
        assert valid
        assert "aether_bot" in msg
        assert "Aether Space" in msg


def test_slack_live_check_invalid_auth():
    conn = SlackConnector()
    creds = {"bot_token": "xoxb-invalid-bot-token"}
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({
        "ok": False,
        "error": "invalid_auth"
    }).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = mock_resp
        valid, msg = conn.verify(creds, live_check=True)
        assert not valid
        assert "invalid" in msg.lower() or "revoked" in msg.lower()


def test_slack_live_check_missing_scope():
    conn = SlackConnector()
    creds = {"bot_token": "xoxb-limited-bot-token"}
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({
        "ok": False,
        "error": "missing_scope",
        "needed": "chat:write"
    }).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = mock_resp
        valid, msg = conn.verify(creds, live_check=True)
        assert not valid
        assert "scope" in msg.lower()


# ============================================================================
# 4. TELEGRAM HARDENING & FINDING 16 TESTS
# ============================================================================

def test_telegram_empty_whitelist_denies_access():
    """FINDING 16: An empty Telegram whitelist MUST NOT permit everyone."""
    conn = TelegramConnector()
    # When allowed_chat_ids is empty or not set
    assert not conn.is_chat_authorized(123456789)
    assert not conn.is_chat_authorized("123456789")

    # With non-empty whitelist
    conn.auth_metadata = {"allowed_chat_ids": ["123456789", "987654321"]}
    assert conn.is_chat_authorized("123456789")
    assert conn.is_chat_authorized(987654321)
    assert not conn.is_chat_authorized("555555555")


def test_telegram_verify_live_check():
    conn = TelegramConnector()
    # 35-char secret conforming to Telegram pattern
    creds = {"bot_token": "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ12345678"}

    # Success case
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({
        "ok": True,
        "result": {"username": "AetherCompanionBot"}
    }).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = mock_resp
        valid, msg = conn.verify(creds, live_check=True)
        assert valid
        assert "AetherCompanionBot" in msg

    # Invalid token (401)
    import urllib.error
    with patch("urllib.request.urlopen") as mock_url:
        mock_url.side_effect = urllib.error.HTTPError("https://api.telegram.org", 401, "Unauthorized", {}, None)
        valid, msg = conn.verify(creds, live_check=True)
        assert not valid
        assert "unauthorized" in msg.lower() or "invalid" in msg.lower()


# ============================================================================
# 5. HTTP CONNECTOR HARDENING TESTS
# ============================================================================

def test_http_format_validation():
    conn = HTTPConnector()
    # Invalid URL scheme
    valid, msg = conn.verify({"base_url": "ftp://example.com"}, live_check=False)
    assert not valid

    # Missing hostname
    valid, msg = conn.verify({"base_url": "http://"}, live_check=False)
    assert not valid

    # Valid
    valid, msg = conn.verify({"base_url": "https://api.example.com/v1"}, live_check=False)
    assert valid


def test_http_live_check_status_codes():
    import urllib.error
    conn = HTTPConnector()
    creds = {"base_url": "https://api.example.com"}

    # 401 Unauthorized
    with patch("urllib.request.urlopen") as mock_url:
        mock_url.side_effect = urllib.error.HTTPError("https://api.example.com", 401, "Unauthorized", {}, None)
        valid, msg = conn.verify(creds, live_check=True)
        assert not valid
        assert "401" in msg or "auth" in msg.lower()

    # 404 Not Found
    with patch("urllib.request.urlopen") as mock_url:
        mock_url.side_effect = urllib.error.HTTPError("https://api.example.com", 404, "Not Found", {}, None)
        valid, msg = conn.verify(creds, live_check=True)
        assert not valid
        assert "404" in msg or "not found" in msg.lower()

    # 429 Rate Limit
    with patch("urllib.request.urlopen") as mock_url:
        mock_url.side_effect = urllib.error.HTTPError("https://api.example.com", 429, "Too Many Requests", {}, None)
        valid, msg = conn.verify(creds, live_check=True)
        assert not valid
        assert "429" in msg or "rate limit" in msg.lower()

    # 500 Server Error
    with patch("urllib.request.urlopen") as mock_url:
        mock_url.side_effect = urllib.error.HTTPError("https://api.example.com", 500, "Internal Server Error", {}, None)
        valid, msg = conn.verify(creds, live_check=True)
        assert not valid
        assert "500" in msg or "server error" in msg.lower()


# ============================================================================
# 6. NOTION CONNECTOR TESTS
# ============================================================================

def test_notion_connector_validation():
    conn = NotionConnector()
    # Missing token
    valid, msg = conn.verify({}, live_check=False)
    assert not valid

    # Bad prefix
    valid, msg = conn.verify({"token": "notion_bad_prefix_123"}, live_check=False)
    assert not valid
    assert "secret_" in msg or "ntn_" in msg

    # Valid secret prefix
    valid, msg = conn.verify({"token": "secret_abc1234567890"}, live_check=False)
    assert valid

    # Valid ntn_ prefix
    valid, msg = conn.verify({"token": "ntn_abc1234567890"}, live_check=False)
    assert valid


def test_notion_live_check_success():
    conn = NotionConnector()
    creds = {"token": "secret_valid_token"}
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({
        "object": "user",
        "id": "bot-id-123",
        "name": "Aether Integration Bot",
        "type": "bot"
    }).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = mock_resp
        valid, msg = conn.verify(creds, live_check=True)
        assert valid
        assert "Aether Integration Bot" in msg


def test_notion_actions_search_and_create_page():
    conn = NotionConnector()
    conn.auth_metadata = {"token": "secret_valid_token", "default_database_id": "db-123"}

    # Mock search
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({
        "results": [{"id": "page-1", "object": "page"}]
    }).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = mock_resp
        search_res = conn.search("roadmap")
        assert len(search_res.get("results", [])) == 1

    # Mock create page
    mock_create_resp = MagicMock()
    mock_create_resp.status = 200
    mock_create_resp.read.return_value = json.dumps({
        "id": "new-page-id",
        "url": "https://notion.so/new-page-id"
    }).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = mock_create_resp
        create_res = conn.create_page(title="Sprint Goals", content="Complete P1.1")
        assert create_res.get("id") == "new-page-id"


# ============================================================================
# 7. OPENAPI CONNECTOR TESTS
# ============================================================================

def test_openapi_connector_spec_loading_and_tools():
    spec_data = {
        "openapi": "3.0.0",
        "info": {"title": "Sample Pet API", "version": "1.0.0"},
        "servers": [{"url": "https://petstore.example.com/api"}],
        "paths": {
            "/pets": {
                "get": {
                    "operationId": "listPets",
                    "summary": "List all pets",
                    "parameters": [{"name": "limit", "in": "query", "schema": {"type": "integer"}}]
                }
            }
        }
    }
    conn = OpenAPIConnector(auth_metadata={"spec_content": spec_data})
    tools = conn.get_tools()
    assert len(tools) == 1
    assert tools[0].name == "listpets"
    assert tools[0].path == "/pets"

    # Reachability test
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b"[]"
    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = mock_resp
        valid, msg = conn.verify({}, live_check=True)
        assert valid
        assert "1 operations" in msg or "operations discovered" in msg



# ============================================================================
# 8. CONNECTION SERVICE & SECRET MASKING INVARIANTS
# ============================================================================

def test_secret_masking_invariants(tmp_path):
    store = ConnectionStore(db_path=tmp_path / "connections.db")
    service = ConnectionService(store=store)

    # Register slack with bot token
    conn = service.connect(
        workspace_id="test_ws",
        provider="slack",
        account_name="Team Slack",
        auth_metadata={"bot_token": "xoxb-sensitive-slack-token-12345", "default_channel": "general"}
    )
    # Status before verification is CONFIGURED or VERIFICATION_REQUIRED
    assert conn.status in (ConnectionStatus.CONFIGURED, ConnectionStatus.VERIFICATION_REQUIRED)

    # to_dict masking
    masked = conn.to_dict(mask_secrets=True)
    assert masked["auth_metadata"]["bot_token"] == "xoxb...345"
    assert masked["auth_metadata"]["default_channel"] == "general"

    # Ensure unmasked access keeps the secret
    unmasked = conn.to_dict(mask_secrets=False)
    assert unmasked["auth_metadata"]["bot_token"] == "xoxb-sensitive-slack-token-12345"

    # Secret preservation on update: Updating account_name without token keeps the existing token
    updated = service.connect(
        workspace_id="test_ws",
        provider="slack",
        account_name="Updated Slack",
        auth_metadata={"default_channel": "announcements"}  # No bot_token passed
    )
    assert updated.auth_metadata["bot_token"] == "xoxb-sensitive-slack-token-12345"
    assert updated.auth_metadata["default_channel"] == "announcements"


def test_truthful_connection_status_transitions(tmp_path):
    store = ConnectionStore(db_path=tmp_path / "connections.db")
    service = ConnectionService(store=store)

    # 1. Not configured
    assert service.get_connection("test_ws", "github") is None

    # 2. Configured without live check
    conn = service.connect(
        workspace_id="test_ws",
        provider="github",
        account_name="Dev GitHub",
        auth_metadata={"token": "ghp_initialtoken"},
        live_check=False
    )
    assert conn.status in (ConnectionStatus.CONFIGURED, ConnectionStatus.VERIFICATION_REQUIRED)

    # 3. Failed verification
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        valid, msg, updated = service.verify_connection("test_ws", "github", live_check=True)
        assert not valid
        assert service.get_connection("test_ws", "github").status == ConnectionStatus.VERIFICATION_FAILED

    # 4. Verified
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({"login": "octocat"}).encode("utf-8")
    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = mock_resp
        valid, msg, updated = service.verify_connection("test_ws", "github", live_check=True)
        assert valid
        assert service.get_connection("test_ws", "github").status == ConnectionStatus.VERIFIED

    # 5. Disconnected
    service.disconnect("test_ws", "github")
    assert service.get_connection("test_ws", "github").status == ConnectionStatus.DISCONNECTED
