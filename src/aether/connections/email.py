"""
Email Connector for Aether (Phase C & Sprint 1).
Provides real SMTP connectivity, verification, and email sending capabilities
with strict credential protection and normalized error handling.
"""
from __future__ import annotations

from datetime import datetime, timezone
import email.utils
from email.message import EmailMessage
import logging
import smtplib
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


class EmailConnector(BaseConnector):
    """
    Real Email connector backed by standard SMTP.
    Works with Gmail, Outlook, Amazon SES, or custom SMTP servers.
    """

    def __init__(self, auth_metadata: dict[str, Any] | None = None) -> None:
        self._auth_metadata = dict(auth_metadata or {})

    @property
    def provider(self) -> str:
        return "email"

    @property
    def capabilities(self) -> list[str]:
        return ["email.send", "email.verify"]

    @property
    def credential_requirements(self) -> list[CredentialRequirement]:
        return [
            CredentialRequirement(
                key="username",
                label="Email Address / Username",
                description="Your email address (e.g. user@gmail.com).",
                required=True,
                secret=False,
            ),
            CredentialRequirement(
                key="password",
                label="Password / App Password",
                description="App password generated from your provider.",
                required=True,
                secret=True,
            ),
            CredentialRequirement(
                key="smtp_host",
                label="SMTP Host",
                description="SMTP server hostname (e.g. smtp.gmail.com).",
                required=True,
                secret=False,
                default="smtp.gmail.com",
            ),
            CredentialRequirement(
                key="smtp_port",
                label="SMTP Port",
                description="Port number (e.g. 587 for TLS, 465 for SSL).",
                required=True,
                secret=False,
                default=587,
            ),
            CredentialRequirement(
                key="use_tls",
                label="Use TLS",
                description="Enable STARTTLS encryption.",
                required=False,
                secret=False,
                default=True,
            ),
        ]

    def _get_config(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = dict(self._auth_metadata)
        if params:
            for k in ("username", "password", "smtp_host", "smtp_port", "use_tls", "from_addr"):
                if k in params and params[k] is not None:
                    merged[k] = params[k]
        return merged

    def verify(self, auth_metadata: dict[str, Any] | None = None, live_check: bool = False) -> tuple[bool, str]:
        meta = auth_metadata or self._auth_metadata
        username = str(meta.get("username") or meta.get("email") or "").strip()
        password = str(meta.get("password") or meta.get("app_password") or meta.get("token") or "").strip()
        host = str(meta.get("smtp_host") or "").strip()
        port = int(meta.get("smtp_port") or 587)
        use_tls = bool(meta.get("use_tls", True))

        if not username:
            return False, "Email address or username is required."
        if not password:
            return False, "App password or token is required."
        if not host:
            return False, "SMTP Host is required (e.g. smtp.gmail.com)."

        # Perform live connection check if requested
        if live_check or meta.get("live_check"):
            try:
                if port == 465:
                    server = smtplib.SMTP_SSL(host, port, timeout=5.0)
                else:
                    server = smtplib.SMTP(host, port, timeout=5.0)
                try:
                    server.ehlo()
                    if use_tls and port != 465:
                        server.starttls()
                        server.ehlo()
                    server.login(username, password)
                    return True, f"SMTP authentication verified successfully for {username}."
                finally:
                    try:
                        server.quit()
                    except Exception:
                        pass
            except smtplib.SMTPAuthenticationError as exc:
                return False, "SMTP authentication failed: Invalid username or app password."
            except smtplib.SMTPConnectError as exc:
                return False, f"Could not connect to SMTP server '{host}:{port}'."
            except Exception as exc:
                return False, f"SMTP verification error: {type(exc).__name__}"

        return True, "Email SMTP credentials format verified."

    def get_health(self) -> ConnectorHealth:
        cfg = self._get_config()
        if not cfg.get("username") or not cfg.get("password"):
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.NOT_CONFIGURED,
                message="Email credentials not configured.",
            )
        valid, msg = self.verify(live_check=True)
        return ConnectorHealth(
            healthy=valid,
            status=ConnectionStatus.VERIFIED if valid else ConnectionStatus.VERIFICATION_FAILED,
            message=msg,
        )

    def send_email(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
        html_body: str | None = None,
        from_addr: str | None = None,
    ) -> dict[str, Any]:
        """
        Sends a real email over SMTP.
        """
        cfg = self._get_config()
        username = str(cfg.get("username") or "").strip()
        password = str(cfg.get("password") or "").strip()
        host = str(cfg.get("smtp_host") or "smtp.gmail.com").strip()
        port = int(cfg.get("smtp_port") or 587)
        use_tls = bool(cfg.get("use_tls", True))

        if not username or not password:
            raise ConnectorConfigurationError(
                "Email credentials are missing. Configure username and password in Connections.",
                provider=self.provider,
            )

        # Build message
        msg = EmailMessage()
        sender = from_addr or username
        msg["From"] = sender

        to_addrs = [t.strip() for t in (to if isinstance(to, list) else to.split(",")) if t.strip()]
        if not to_addrs:
            raise ConnectorError("At least one recipient ('to') address is required.", provider=self.provider)
        msg["To"] = ", ".join(to_addrs)
        msg["Subject"] = subject
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["Message-ID"] = email.utils.make_msgid(domain=host if "." in host else "aether.local")

        all_recipients = list(to_addrs)
        if cc:
            cc_addrs = [c.strip() for c in (cc if isinstance(cc, list) else cc.split(",")) if c.strip()]
            if cc_addrs:
                msg["Cc"] = ", ".join(cc_addrs)
                all_recipients.extend(cc_addrs)

        if bcc:
            bcc_addrs = [b.strip() for b in (bcc if isinstance(bcc, list) else bcc.split(",")) if b.strip()]
            all_recipients.extend(bcc_addrs)

        msg.set_content(body)
        if html_body:
            msg.add_alternative(html_body, subtype="html")

        try:
            if port == 465:
                server = smtplib.SMTP_SSL(host, port, timeout=15.0)
            else:
                server = smtplib.SMTP(host, port, timeout=15.0)
            try:
                server.ehlo()
                if use_tls and port != 465:
                    server.starttls()
                    server.ehlo()
                server.login(username, password)
                server.send_message(msg, from_addr=sender, to_addrs=all_recipients)
            finally:
                try:
                    server.quit()
                except Exception:
                    pass
        except smtplib.SMTPAuthenticationError:
            raise ConnectorAuthError(
                "Failed to authenticate with SMTP server. Check username or application password.",
                provider=self.provider,
            ) from None
        except smtplib.SMTPRecipientsRefused as exc:
            raise ConnectorError(f"Recipient address refused by server: {exc}", provider=self.provider) from None
        except (smtplib.SMTPException, OSError) as exc:
            raise ConnectorError(f"SMTP send failed: {type(exc).__name__} - {exc}", provider=self.provider) from None

        return {
            "status": "sent",
            "message_id": msg["Message-ID"],
            "to": to_addrs,
            "subject": subject,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }

    def execute(self, operation: str, params: dict[str, Any]) -> ConnectorResult:
        clean_op = operation.lower().strip()
        if clean_op in ("email.send", "send", "send_email"):
            to = params.get("to") or params.get("recipient")
            if not to:
                raise ConnectorError("Recipient 'to' is required.", provider=self.provider)
            subject = str(params.get("subject") or "Message from Aether")
            body = str(params.get("body") or params.get("content") or "")
            cc = params.get("cc")
            bcc = params.get("bcc")
            html_body = params.get("html") or params.get("html_body")
            from_addr = params.get("from_addr") or params.get("sender")

            res = self.send_email(
                to=to,
                subject=subject,
                body=body,
                cc=cc,
                bcc=bcc,
                html_body=html_body,
                from_addr=from_addr,
            )
            return ConnectorResult(
                success=True,
                operation=operation,
                provider=self.provider,
                data=res,
            )

        elif clean_op in ("email.verify", "verify"):
            valid, msg = self.verify(params)
            return ConnectorResult(
                success=valid,
                operation=operation,
                provider=self.provider,
                data={"valid": valid, "message": msg},
                error=None if valid else msg,
            )

        else:
            raise ConnectorError(f"Unsupported Email operation: '{operation}'", provider=self.provider)
