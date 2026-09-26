"""
Telegram Connector for Aether (Phase C & Macro Step 6).
Provides real Telegram Bot integration for mobile companion interaction,
action approval flows, real-time alerts, and conversational workforce delegation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from aether.connections.base import (
    BaseConnector,
    ConnectorAuthError,
    ConnectorConfigurationError,
    ConnectorError,
    ConnectorHealth,
    ConnectorResult,
    CredentialRequirement,
)
from aether.connections.models import ConnectionStatus

logger = logging.getLogger(__name__)


class TelegramConnector(BaseConnector):
    """
    Real Telegram Bot Connector using Telegram Bot API.
    Enables remote command execution, inline interactive approvals, and mobile notifications.
    """

    API_BASE = "https://api.telegram.org"

    def __init__(self, auth_metadata: dict[str, Any] | None = None) -> None:
        self._auth_metadata = dict(auth_metadata or {})

    @property
    def provider(self) -> str:
        return "telegram"

    @property
    def capabilities(self) -> list[str]:
        return [
            "telegram.send_message",
            "telegram.send_approval",
            "telegram.verify",
        ]

    @property
    def credential_requirements(self) -> list[CredentialRequirement]:
        return [
            CredentialRequirement(
                key="bot_token",
                label="Telegram Bot Token",
                description="Token provided by @BotFather (e.g. 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ).",
                required=True,
                secret=True,
            ),
            CredentialRequirement(
                key="default_chat_id",
                label="Default Chat ID",
                description="Your personal or group Chat ID (e.g. 987654321).",
                required=False,
                secret=False,
            ),
            CredentialRequirement(
                key="allowed_chat_ids",
                label="Authorized Chat IDs",
                description="Comma-separated list of Chat IDs authorized to interact with Aether.",
                required=False,
                secret=False,
            ),
        ]

    def _get_token(self, params: dict[str, Any] | None = None) -> str | None:
        meta = dict(self._auth_metadata)
        if params and "bot_token" in params and params["bot_token"]:
            meta["bot_token"] = params["bot_token"]
        token = str(meta.get("bot_token") or meta.get("token") or "").strip()
        return token or None

    def _get_default_chat_id(self, params: dict[str, Any] | None = None) -> str | None:
        meta = dict(self._auth_metadata)
        if params and "chat_id" in params and params["chat_id"]:
            return str(params["chat_id"]).strip()
        cid = meta.get("default_chat_id") or meta.get("chat_id")
        return str(cid).strip() if cid else None

    def _get_allowed_chat_ids(self) -> list[str]:
        raw = self._auth_metadata.get("allowed_chat_ids") or ""
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        if isinstance(raw, str) and raw.strip():
            return [x.strip() for x in raw.split(",") if x.strip()]
        default_id = self._get_default_chat_id()
        return [default_id] if default_id else []

    def is_chat_authorized(self, chat_id: str | int) -> bool:
        allowed = self._get_allowed_chat_ids()
        if not allowed:
            # Finding 16 & Macro-pass P1.1: Deny by default if whitelist is empty
            return False
        return str(chat_id).strip() in allowed

    def verify(self, auth_metadata: dict[str, Any] | None = None, live_check: bool = False) -> tuple[bool, str]:
        meta = auth_metadata or self._auth_metadata
        token = str(meta.get("bot_token") or meta.get("token") or "").strip()

        if not token:
            return False, "Telegram Bot Token is required."

        # Validate token pattern (digits:alphanumeric)
        pattern = r"^\d{8,12}:[A-Za-z0-9_-]{30,50}$"
        if not re.match(pattern, token):
            return False, "Invalid Telegram Bot Token format. Expected format: <id>:<alphanumeric_secret>."

        if live_check or meta.get("live_check"):
            try:
                url = f"{self.API_BASE}/bot{token}/getMe"
                req = urllib.request.Request(url, headers={"User-Agent": "Aether/1.0"}, method="GET")
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("ok"):
                        bot_info = data.get("result", {})
                        username = bot_info.get("username", "UnknownBot")
                        return True, f"Telegram Bot @{username} verified successfully."
                    return False, f"Telegram error: {data.get('description', 'Unknown error')}"
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 404):
                    return False, f"Telegram bot token authentication failed (HTTP {exc.code}): invalid token or bot not found."
                return False, f"Telegram API HTTP error (HTTP {exc.code}): {exc.reason}"
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                return False, f"Failed to contact Telegram API: {exc}"
            except Exception as e:
                return False, f"Telegram live verification failed: {e}"

        return True, "Telegram Bot Token format verified."

    def get_health(self) -> ConnectorHealth:
        token = self._get_token()
        if not token:
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.NOT_CONFIGURED,
                message="Telegram Bot Token not configured.",
            )
        valid, msg = self.verify(live_check=True)
        return ConnectorHealth(
            healthy=valid,
            status=ConnectionStatus.VERIFIED if valid else ConnectionStatus.VERIFICATION_FAILED,
            message=msg,
        )

    def send_message(
        self,
        chat_id: str | int | None = None,
        text: str = "",
        reply_markup: dict[str, Any] | None = None,
        parse_mode: str = "Markdown",
        disable_web_page_preview: bool = True,
    ) -> dict[str, Any]:
        """
        Sends a message to a Telegram chat.
        """
        token = self._get_token()
        if not token:
            raise ConnectorConfigurationError("Telegram Bot Token is not configured.", provider=self.provider)

        target_chat_id = chat_id or self._get_default_chat_id()
        if not target_chat_id:
            raise ConnectorConfigurationError("Target chat_id is required to send Telegram message.", provider=self.provider)

        url = f"{self.API_BASE}/bot{token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": target_chat_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json", "User-Agent": "Aether/1.0"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                if not res_data.get("ok"):
                    raise ConnectorError(
                        f"Telegram API error: {res_data.get('description', 'Unknown error')}",
                        provider=self.provider,
                    )
                return res_data.get("result", {})
        except urllib.error.HTTPError as http_err:
            body = ""
            try:
                body = http_err.read().decode("utf-8")
            except Exception:
                pass
            raise ConnectorError(f"HTTP {http_err.code}: {body or http_err.reason}", provider=self.provider)
        except Exception as exc:
            raise ConnectorError(f"Failed to send Telegram message: {exc}", provider=self.provider)

    def send_approval_request(
        self,
        chat_id: str | int | None,
        action_id: str,
        execution_id: str,
        title: str,
        description: str,
    ) -> dict[str, Any]:
        """
        Sends an interactive message with inline [Approve] / [Reject] buttons.
        """
        text = (
            f"🛡️ *Richiesta di Approvazione Aether*\n\n"
            f"*Azione:* `{action_id}`\n"
            f"*Oggetto:* {title}\n"
            f"_{description}_\n\n"
            f"Tocca un pulsante per confermare o rifiutare l'esecuzione:"
        )

        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approva ed Esegui", "callback_data": f"approve:{execution_id}"},
                    {"text": "❌ Rifiuta", "callback_data": f"reject:{execution_id}"},
                ]
            ]
        }

        return self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: str = "",
        show_alert: bool = False,
    ) -> bool:
        """Acknowledges an inline button callback click."""
        token = self._get_token()
        if not token:
            return False

        url = f"{self.API_BASE}/bot{token}/answerCallbackQuery"
        payload = {
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": show_alert,
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json", "User-Agent": "Aether/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return bool(data.get("ok"))
        except Exception:
            return False

    def edit_message_text(
        self,
        chat_id: str | int,
        message_id: int,
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Edits an existing Telegram message (e.g. after approval button is clicked)."""
        token = self._get_token()
        if not token:
            return {}

        url = f"{self.API_BASE}/bot{token}/editMessageText"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json", "User-Agent": "Aether/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("result", {})
        except Exception as e:
            logger.warning(f"Could not edit Telegram message {message_id}: {e}")
            return {}

    def get_updates(self, offset: int | None = None, timeout: int = 10) -> list[dict[str, Any]]:
        """Retrieves incoming updates via long polling."""
        token = self._get_token()
        if not token:
            return []

        url = f"{self.API_BASE}/bot{token}/getUpdates?timeout={timeout}"
        if offset is not None:
            url += f"&offset={offset}"

        req = urllib.request.Request(url, headers={"User-Agent": "Aether/1.0"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    return data.get("result", [])
                return []
        except Exception as e:
            logger.debug(f"Failed to get Telegram updates: {e}")
            return []

    def execute(self, operation: str, params: dict[str, Any]) -> ConnectorResult:
        clean_op = operation.lower().strip()
        try:
            if clean_op in ("telegram.send_message", "send_message"):
                chat_id = params.get("chat_id")
                text = params.get("text", "")
                parse_mode = params.get("parse_mode", "Markdown")
                res = self.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
                return ConnectorResult(
                    success=True,
                    operation=operation,
                    provider=self.provider,
                    data={"message_id": res.get("message_id"), "chat_id": res.get("chat", {}).get("id")},
                )
            elif clean_op in ("telegram.send_approval", "send_approval"):
                chat_id = params.get("chat_id")
                action_id = params.get("action_id", "")
                execution_id = params.get("execution_id", "")
                title = params.get("title", "")
                description = params.get("description", "")
                res = self.send_approval_request(
                    chat_id=chat_id,
                    action_id=action_id,
                    execution_id=execution_id,
                    title=title,
                    description=description,
                )
                return ConnectorResult(
                    success=True,
                    operation=operation,
                    provider=self.provider,
                    data={"message_id": res.get("message_id")},
                )
            raise ValueError(f"Unsupported Telegram operation: '{operation}'")
        except ConnectorError as e:
            return ConnectorResult(success=False, operation=operation, provider=self.provider, error=e.message)
        except Exception as exc:
            return ConnectorResult(success=False, operation=operation, provider=self.provider, error=str(exc))
