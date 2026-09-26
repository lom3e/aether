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
import socket
import ssl
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
                label="Use STARTTLS",
                description="Enable STARTTLS encryption (typically port 587).",
                required=False,
                secret=False,
                default=True,
            ),
            CredentialRequirement(
                key="use_ssl",
                label="Use Direct SSL",
                description="Enable direct SSL/TLS encryption (typically port 465).",
                required=False,
                secret=False,
                default=False,
            ),
            CredentialRequirement(
                key="sender_address",
                label="Sender Address / Name",
                description="Optional custom sender address or display name.",
                required=False,
                secret=False,
            ),
            CredentialRequirement(
                key="test_recipient",
                label="Test Recipient",
                description="Optional email address to send a test message during live verification.",
                required=False,
                secret=False,
            ),
        ]

    def _get_config(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = dict(self._auth_metadata)
        if params:
            for k in (
                "username", "password", "smtp_host", "smtp_port",
                "use_tls", "use_ssl", "sender_address", "from_addr", "test_recipient",
            ):
                if k in params and params[k] is not None:
                    merged[k] = params[k]
        return merged

    def verify(self, auth_metadata: dict[str, Any] | None = None, live_check: bool = False) -> tuple[bool, str]:
        meta = auth_metadata or self._auth_metadata
        username = str(meta.get("username") or meta.get("email") or "").strip()
        password = str(meta.get("password") or meta.get("app_password") or meta.get("token") or "").strip()
        host = str(meta.get("smtp_host") or "").strip()
        try:
            port = int(meta.get("smtp_port") or 587)
        except (ValueError, TypeError):
            return False, "SMTP Port must be a valid integer."
        if port <= 0 or port > 65535:
            return False, "SMTP Port must be between 1 and 65535."

        use_tls = bool(meta.get("use_tls", True))
        use_ssl = bool(meta.get("use_ssl", False)) or port == 465

        if not username:
            return False, "Email address or username is required."
        if not password:
            return False, "App password or token is required."
        if not host:
            return False, "SMTP Host is required (e.g. smtp.gmail.com)."

        # Perform live connection check if requested
        if live_check or meta.get("live_check"):
            try:
                if use_ssl:
                    server = smtplib.SMTP_SSL(host, port, timeout=7.0)
                else:
                    server = smtplib.SMTP(host, port, timeout=7.0)
                try:
                    server.ehlo()
                    if use_tls and not use_ssl:
                        server.starttls()
                        server.ehlo()
                    server.login(username, password)

                    # Optional test recipient verification
                    test_recipient = str(meta.get("test_recipient") or "").strip()
                    if test_recipient:
                        sender = str(meta.get("sender_address") or meta.get("from_addr") or username).strip()
                        msg = EmailMessage()
                        msg["From"] = sender
                        msg["To"] = test_recipient
                        msg["Subject"] = "Aether Verification Test"
                        msg["Date"] = email.utils.formatdate(localtime=True)
                        msg.set_content("This is an automated test message from Aether to verify SMTP credentials.")
                        server.send_message(msg)
                        return True, f"SMTP connection verified and test email delivered to {test_recipient}."

                    return True, f"SMTP authentication verified successfully for {username} via {host}:{port}."
                finally:
                    try:
                        server.quit()
                    except Exception:
                        pass
            except socket.gaierror as exc:
                return False, f"SMTP DNS resolution failed for host '{host}': {exc}"
            except (TimeoutError, socket.timeout):
                return False, f"SMTP connection timed out connecting to '{host}:{port}'."
            except ssl.SSLError as exc:
                return False, f"SMTP SSL/TLS handshake failed on '{host}:{port}': {exc}"
            except smtplib.SMTPNotSupportedError as exc:
                return False, f"SMTP STARTTLS is not supported by '{host}': {exc}"
            except smtplib.SMTPAuthenticationError:
                return False, "SMTP authentication failed: Invalid username or app password."
            except (smtplib.SMTPConnectError, ConnectionRefusedError):
                return False, f"Could not connect to SMTP server '{host}:{port}': server unavailable or connection refused."
            except smtplib.SMTPServerDisconnected as exc:
                return False, f"SMTP server disconnected unexpectedly: {exc}"
            except smtplib.SMTPRecipientsRefused as exc:
                return False, f"SMTP test recipient refused by server: {exc}"
            except smtplib.SMTPException as exc:
                return False, f"SMTP error: {exc}"
            except Exception as exc:
                return False, f"SMTP verification error: {type(exc).__name__} - {exc}"

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
        use_ssl = bool(cfg.get("use_ssl", False)) or port == 465
        default_sender = str(cfg.get("sender_address") or username).strip()

        if not username or not password:
            raise ConnectorConfigurationError(
                "Email credentials are missing. Configure username and password in Connections.",
                provider=self.provider,
            )

        # Build message
        msg = EmailMessage()
        sender = from_addr or default_sender
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
            if use_ssl:
                server = smtplib.SMTP_SSL(host, port, timeout=15.0)
            else:
                server = smtplib.SMTP(host, port, timeout=15.0)
            try:
                server.ehlo()
                if use_tls and not use_ssl:
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
