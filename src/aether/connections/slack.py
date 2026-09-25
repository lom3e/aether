"""
Slack Connector for Aether (Phase C & Sprint 1).
Supports message dispatching via Incoming Webhook and Bot User OAuth Token (xoxb-...)
with connection verification, truthful delivery status, and credential security.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import urllib.error
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


class SlackConnector(BaseConnector):
    """
    Real Slack connector supporting Bot Token (xoxb-...) and Incoming Webhooks.
    """

    DEFAULT_API_BASE = "https://slack.com/api"

    def __init__(self, auth_metadata: dict[str, Any] | None = None) -> None:
        self._auth_metadata = dict(auth_metadata or {})

    @property
    def provider(self) -> str:
        return "slack"

    @property
    def capabilities(self) -> list[str]:
        return ["slack.send_message", "slack.verify"]

    @property
    def credential_requirements(self) -> list[CredentialRequirement]:
        return [
            CredentialRequirement(
                key="bot_token",
                label="Bot User OAuth Token",
                description="Slack Bot Token starting with xoxb-... (for channel & direct messaging).",
                required=False,
                secret=True,
            ),
            CredentialRequirement(
                key="webhook_url",
                label="Incoming Webhook URL",
                description="Slack Webhook URL starting with https://hooks.slack.com/...",
                required=False,
                secret=True,
            ),
            CredentialRequirement(
                key="default_channel",
                label="Default Channel",
                description="Default target channel (e.g. #general).",
                required=False,
                secret=False,
            ),
        ]

    def _get_credentials(self, params: dict[str, Any] | None = None) -> tuple[str | None, str | None]:
        meta = dict(self._auth_metadata)
        if params:
            for k in ("bot_token", "token", "webhook_url", "default_channel"):
                if k in params and params[k]:
                    meta[k] = params[k]

        bot_token = str(meta.get("bot_token") or meta.get("token") or "").strip() or None
        webhook_url = str(meta.get("webhook_url") or "").strip() or None
        return bot_token, webhook_url

    def verify(self, auth_metadata: dict[str, Any] | None = None, live_check: bool = False) -> tuple[bool, str]:
        meta = auth_metadata or self._auth_metadata
        bot_token = str(meta.get("bot_token") or meta.get("token") or "").strip()
        webhook_url = str(meta.get("webhook_url") or "").strip()

        if not bot_token and not webhook_url:
            return False, "Slack Bot User OAuth Token (xoxb-...) or Incoming Webhook URL is required."

        if bot_token and not (bot_token.startswith("xoxb-") or bot_token.startswith("xoxp-") or len(bot_token) > 20):
            return False, "Invalid Slack Bot Token format. Token should start with 'xoxb-'."

        if webhook_url and not webhook_url.startswith("https://hooks.slack.com/"):
            return False, "Invalid Slack Webhook URL. Must start with 'https://hooks.slack.com/'."

        if (live_check or meta.get("live_check")) and bot_token:
            try:
                req = urllib.request.Request(
                    f"{self.DEFAULT_API_BASE}/auth.test",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("ok"):
                        user = data.get("user") or "bot"
                        team = data.get("team") or "workspace"
                        return True, f"Slack bot authenticated as @{user} in team '{team}'."
                    else:
                        return False, f"Slack authentication failed: {data.get('error', 'unknown error')}"
            except Exception as exc:
                return False, f"Slack live verification error: {type(exc).__name__}"

        return True, "Slack credentials format verified."

    def get_health(self) -> ConnectorHealth:
        bot_token, webhook_url = self._get_credentials()
        if not bot_token and not webhook_url:
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.NOT_CONFIGURED,
                message="Slack credentials not configured.",
            )
        valid, msg = self.verify(live_check=True)
        return ConnectorHealth(
            healthy=valid,
            status=ConnectionStatus.VERIFIED if valid else ConnectionStatus.VERIFICATION_FAILED,
            message=msg,
        )

    def send_message(
        self,
        text: str,
        channel: str | None = None,
        blocks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Sends a message to Slack via Bot Token or Webhook.
        """
        bot_token, webhook_url = self._get_credentials()

        if not bot_token and not webhook_url:
            raise ConnectorConfigurationError(
                "Slack credentials are missing. Configure a Bot Token or Webhook in Connections.",
                provider=self.provider,
            )

        if not text and not blocks:
            raise ConnectorError("Message text or blocks must be provided.", provider=self.provider)

        target_channel = channel or self._auth_metadata.get("default_channel")

        # 1. Prefer Bot Token API if available
        if bot_token:
            clean_chan = target_channel or "general"
            if clean_chan.startswith("#"):
                clean_chan = clean_chan[1:]
            payload: dict[str, Any] = {
                "channel": clean_chan,
                "text": text,
            }
            if blocks:
                payload["blocks"] = blocks

            headers = {
                "Authorization": f"Bearer {bot_token}",
                "Content-Type": "application/json; charset=utf-8",
            }
            req = urllib.request.Request(
                f"{self.DEFAULT_API_BASE}/chat.postMessage",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    res_data = json.loads(resp.read().decode("utf-8"))
                    if not res_data.get("ok"):
                        err_code = res_data.get("error", "unknown_error")
                        if err_code in ("invalid_auth", "not_authed", "account_inactive", "token_revoked"):
                            raise ConnectorAuthError(f"Slack authorization failed ({err_code}).", provider=self.provider)
                        raise ConnectorError(f"Slack delivery error: {err_code}", provider=self.provider)

                    return {
                        "status": "delivered",
                        "channel": clean_chan,
                        "ts": res_data.get("ts"),
                        "message_id": res_data.get("message", {}).get("bot_id") or res_data.get("ts"),
                        "sent_at": datetime.now(timezone.utc).isoformat(),
                    }
            except (ConnectorAuthError, ConnectorError):
                raise
            except Exception as exc:
                raise ConnectorError(f"Failed to post to Slack: {type(exc).__name__} - {exc}", provider=self.provider) from None

        # 2. Webhook delivery path
        if webhook_url:
            payload = {"text": text}
            if target_channel:
                payload["channel"] = target_channel
            if blocks:
                payload["blocks"] = blocks

            headers = {"Content-Type": "application/json"}
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    resp_body = resp.read().decode("utf-8").strip()
                    if resp_body.lower() != "ok" and resp.status >= 400:
                        raise ConnectorError(f"Slack webhook returned: {resp_body}", provider=self.provider)
                    return {
                        "status": "delivered",
                        "channel": target_channel or "webhook-default",
                        "sent_at": datetime.now(timezone.utc).isoformat(),
                    }
            except Exception as exc:
                raise ConnectorError(f"Failed to deliver Slack webhook: {type(exc).__name__} - {exc}", provider=self.provider) from None

        raise ConnectorConfigurationError("No valid Slack delivery path available.", provider=self.provider)

    def execute(self, operation: str, params: dict[str, Any]) -> ConnectorResult:
        clean_op = operation.lower().strip()
        if clean_op in ("slack.send_message", "send_message", "post_message"):
            text = str(params.get("text") or params.get("message") or params.get("content") or "").strip()
            channel = params.get("channel")
            blocks = params.get("blocks")
            res = self.send_message(text=text, channel=channel, blocks=blocks)
            return ConnectorResult(
                success=True,
                operation=operation,
                provider=self.provider,
                data=res,
            )

        elif clean_op in ("slack.verify", "verify"):
            valid, msg = self.verify(params)
            return ConnectorResult(
                success=valid,
                operation=operation,
                provider=self.provider,
                data={"valid": valid, "message": msg},
                error=None if valid else msg,
            )

        else:
            raise ConnectorError(f"Unsupported Slack operation: '{operation}'", provider=self.provider)
