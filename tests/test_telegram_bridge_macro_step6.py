import http.server
import json
import socket
import threading
import time
from pathlib import Path
from typing import Any
import pytest
from unittest.mock import MagicMock

from aether.connections.models import Connection, ConnectionStatus
from aether.connections.service import ConnectionService
from aether.connections.store import ConnectionStore
from aether.connections.telegram import TelegramConnector
from aether.connections.telegram_bridge import TelegramBridge
from aether.actions.registry import ActionRegistry, ActionTier, ActionPermissionLevel
from aether.actions.executor import ActionExecutor
from aether.actions.store import ActionStore
from aether.notifications.service import NotificationService
from aether.notifications.store import NotificationStore
from aether.notifications.models import NotificationType, NotificationPriority
from aether.personal.models import IntentTier, UserIntent, PersonalStep
from aether.personal.service import PersonalAgentService


class MockTelegramServerHandler(http.server.BaseHTTPRequestHandler):
    recorded_requests: list[dict[str, Any]] = []

    def do_GET(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
        MockTelegramServerHandler.recorded_requests.append({
            "method": "GET",
            "path": self.path,
            "body": body,
        })

        if "getMe" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "result": {
                    "id": 999888777,
                    "is_bot": True,
                    "first_name": "AetherBot",
                    "username": "AetherCompanionBot"
                }
            }).encode("utf-8"))
            return

        if "getUpdates" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "result": [
                    {
                        "update_id": 1001,
                        "message": {
                            "message_id": 50,
                            "chat": {"id": 12345},
                            "text": "Ciao Aether",
                        }
                    }
                ]
            }).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
        data = json.loads(body) if body else {}

        MockTelegramServerHandler.recorded_requests.append({
            "method": "POST",
            "path": self.path,
            "body": data,
        })

        if "sendMessage" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "result": {
                    "message_id": 101,
                    "chat": {"id": data.get("chat_id")},
                    "text": data.get("text"),
                }
            }).encode("utf-8"))
            return

        if "answerCallbackQuery" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "result": True
            }).encode("utf-8"))
            return

        if "editMessageText" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "result": {
                    "message_id": data.get("message_id"),
                    "chat": {"id": data.get("chat_id")},
                    "text": data.get("text"),
                }
            }).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture
def mock_telegram_server():
    MockTelegramServerHandler.recorded_requests.clear()
    server = http.server.HTTPServer(("127.0.0.1", 0), MockTelegramServerHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    orig_base = TelegramConnector.API_BASE
    TelegramConnector.API_BASE = f"http://127.0.0.1:{port}"

    yield f"http://127.0.0.1:{port}"

    TelegramConnector.API_BASE = orig_base
    server.shutdown()
    server.server_close()


def test_telegram_connector_token_validation_and_live_check(mock_telegram_server):
    """Verifies Telegram token format checking and live getMe query."""
    # Invalid token format
    c_bad = TelegramConnector(auth_metadata={"bot_token": "invalid_token"})
    valid, msg = c_bad.verify()
    assert not valid
    assert "Invalid Telegram Bot Token format" in msg

    # Valid token format
    valid_token = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ123456"
    c_good = TelegramConnector(auth_metadata={"bot_token": valid_token})
    valid, msg = c_good.verify(live_check=True)
    assert valid
    assert "@AetherCompanionBot verified successfully" in msg


def test_telegram_connector_send_message_and_approval(mock_telegram_server):
    """Verifies sending messages and inline approval requests with keyboard markup."""
    token = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ123456"
    connector = TelegramConnector(auth_metadata={"bot_token": token, "default_chat_id": "98765"})

    # Send plain message
    res = connector.send_message(text="Hello from Aether!")
    assert res.get("message_id") == 101

    last_req = MockTelegramServerHandler.recorded_requests[-1]
    assert last_req["path"] == f"/bot{token}/sendMessage"
    assert last_req["body"]["chat_id"] == "98765"
    assert last_req["body"]["text"] == "Hello from Aether!"

    # Send approval request
    res_app = connector.send_approval_request(
        chat_id="98765",
        action_id="email.send",
        execution_id="exec-42",
        title="Send recap email",
        description="Will send email to client@example.com",
    )
    assert res_app.get("message_id") == 101
    last_app_req = MockTelegramServerHandler.recorded_requests[-1]
    assert "inline_keyboard" in last_app_req["body"]["reply_markup"]
    buttons = last_app_req["body"]["reply_markup"]["inline_keyboard"][0]
    assert buttons[0]["callback_data"] == "approve:exec-42"
    assert buttons[1]["callback_data"] == "reject:exec-42"


def test_telegram_connector_chat_authorization():
    """Verifies whitelist filtering on authorized chats."""
    token = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ123456"

    # Whitelist specified
    c_restricted = TelegramConnector(auth_metadata={
        "bot_token": token,
        "default_chat_id": "111",
        "allowed_chat_ids": "111, 222, 333",
    })
    assert c_restricted.is_chat_authorized(111)
    assert c_restricted.is_chat_authorized("222")
    assert not c_restricted.is_chat_authorized(444)

    # No whitelist specified -> default is denied for security (Finding 16 & P1.1)
    c_open = TelegramConnector(auth_metadata={"bot_token": token})
    assert not c_open.is_chat_authorized(99999)


def test_telegram_bridge_start_welcome(mock_telegram_server):
    """Verifies /start returns the helpful welcome message."""
    mock_ws = MagicMock()
    mock_conn = Connection(
        id="c-tg",
        workspace_id="default",
        provider="telegram",
        account_name="Telegram Companion",
        status=ConnectionStatus.CONNECTED,
        auth_metadata={"bot_token": "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ123456", "default_chat_id": "12345"},
    )
    mock_ws.name = "default"
    mock_ws.connections.get_connection.return_value = mock_conn

    update = {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "chat": {"id": 12345},
            "text": "/start",
        }
    }

    result = TelegramBridge.handle_update(update, mock_ws)
    assert result["status"] == "welcome_sent"
    last_req = MockTelegramServerHandler.recorded_requests[-1]
    assert "Benvenuto su Aether" in last_req["body"]["text"]


def test_telegram_bridge_unauthorized_chat(mock_telegram_server):
    """Verifies access rejection when chat is not in authorized list."""
    mock_ws = MagicMock()
    mock_conn = Connection(
        id="c-tg",
        workspace_id="default",
        provider="telegram",
        account_name="Telegram Companion",
        status=ConnectionStatus.CONNECTED,
        auth_metadata={
            "bot_token": "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ123456",
            "allowed_chat_ids": "12345",
        },
    )
    mock_ws.name = "default"
    mock_ws.connections.get_connection.return_value = mock_conn

    update = {
        "update_id": 2,
        "message": {
            "message_id": 11,
            "chat": {"id": 99999},  # Unauthorized
            "text": "Qualcosa",
        }
    }

    result = TelegramBridge.handle_update(update, mock_ws)
    assert result["status"] == "unauthorized"
    last_req = MockTelegramServerHandler.recorded_requests[-1]
    assert "Accesso Negato" in last_req["body"]["text"]


def test_telegram_bridge_prompt_processing_and_pending_approval(mock_telegram_server):
    """Verifies that user prompts needing approval trigger send_approval_request with buttons."""
    mock_ws = MagicMock()
    mock_conn = Connection(
        id="c-tg",
        workspace_id="default",
        provider="telegram",
        account_name="Telegram Companion",
        status=ConnectionStatus.CONNECTED,
        auth_metadata={"bot_token": "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ123456", "default_chat_id": "12345"},
    )
    mock_ws.name = "default"
    mock_ws.connections.get_connection.return_value = mock_conn

    # Setup mock personal response with pending_approval
    fake_step = MagicMock()
    fake_step.status = "pending_approval"
    fake_step.details = {"action_id": "email.send"}

    fake_reply = MagicMock()
    fake_reply.steps = [fake_step]
    fake_reply.action_execution_id = "exec-test-77"
    fake_reply.content = "Richiesta di invio email in attesa di autorizzazione."
    mock_ws.personal.process_prompt.return_value = fake_reply

    update = {
        "update_id": 3,
        "message": {
            "message_id": 12,
            "chat": {"id": 12345},
            "text": "Invia una email al cliente",
        }
    }

    result = TelegramBridge.handle_update(update, mock_ws)
    assert result["status"] == "processed"

    # Verify that an approval request was sent with inline buttons
    last_req = MockTelegramServerHandler.recorded_requests[-1]
    assert "Richiesta di Approvazione Aether" in last_req["body"]["text"]
    assert last_req["body"]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "approve:exec-test-77"


def test_telegram_bridge_callback_query_approval(mock_telegram_server):
    """Verifies clicking the inline [Approve] button executes the action and updates the message."""
    mock_ws = MagicMock()
    mock_conn = Connection(
        id="c-tg",
        workspace_id="default",
        provider="telegram",
        account_name="Telegram Companion",
        status=ConnectionStatus.CONNECTED,
        auth_metadata={"bot_token": "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ123456", "default_chat_id": "12345"},
    )
    mock_ws.name = "default"
    mock_ws.connections.get_connection.return_value = mock_conn

    exec_result = MagicMock()
    exec_result.status.value = "completed"
    mock_ws.action_executor.approve_execution.return_value = exec_result

    update = {
        "update_id": 4,
        "callback_query": {
            "id": "cb-99",
            "data": "approve:exec-test-77",
            "message": {
                "message_id": 105,
                "chat": {"id": 12345},
            },
        }
    }

    result = TelegramBridge.handle_update(update, mock_ws)
    assert result["status"] == "approved"
    assert result["execution_id"] == "exec-test-77"

    mock_ws.action_executor.approve_execution.assert_called_once_with("exec-test-77")

    # Verify editMessageText was called
    edit_req = next(r for r in MockTelegramServerHandler.recorded_requests if "editMessageText" in r["path"])
    assert "Azione Approvata ed Eseguita con Successo" in edit_req["body"]["text"]


def test_notification_service_mirrors_to_telegram(mock_telegram_server, tmp_path):
    """Verifies that high priority and approval notifications are mirrored to Telegram."""
    notif_db = tmp_path / "notif.db"
    store = NotificationStore(str(notif_db))
    conn_store = ConnectionStore(str(tmp_path / "conn.db"))
    conn_svc = ConnectionService(conn_store)

    conn_svc.connect(
        workspace_id="ws-test",
        provider="telegram",
        account_name="Bot",
        auth_metadata={"bot_token": "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ123456", "default_chat_id": "777888"},
    )

    notif_svc = NotificationService(store=store, connection_service=conn_svc)

    # 1. High priority notification
    notif_svc.notify(
        workspace_id="ws-test",
        type=NotificationType.ACTION_FAILED,
        title="Critical Disk Alert",
        message="Disk space is under 5%",
        priority=NotificationPriority.HIGH,
    )

    last_req = MockTelegramServerHandler.recorded_requests[-1]
    assert last_req["path"] == "/bot123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ123456/sendMessage"
    assert "Critical Disk Alert" in last_req["body"]["text"]
    assert last_req["body"]["chat_id"] == "777888"

    # 2. Approval notification
    notif_svc.notify_approval(
        workspace_id="ws-test",
        title="Database migration",
        message="Approve applying migration v2",
        action_id="db.migrate",
        execution_id="exec-mig-1",
        prompt="run migration",
    )

    last_req2 = MockTelegramServerHandler.recorded_requests[-1]
    assert "approve:exec-mig-1" in str(last_req2["body"]["reply_markup"])
