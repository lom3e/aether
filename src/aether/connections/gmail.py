"""Gmail, read-only: list and read your mail on this computer.

Built on the Google connector (same token refresh, same revocation handling). Only the gmail.readonly scope is requested:
Aether can never send, delete or change mail through it. Listing mail does not send its content to any AI model; only an
explicit request to summarise a message would, through the normal (masked, recorded) path.
"""
from __future__ import annotations

import base64
import html
import re
from typing import Any

from aether.connections.google_calendar import GoogleCalendarConnector

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
GMAIL_SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/gmail.readonly"]


def _header(headers: list[dict[str, Any]], name: str) -> str:
    return next((h.get("value", "") for h in headers or [] if str(h.get("name", "")).lower() == name.lower()), "")


def _sender_name(raw: str) -> str:
    m = re.match(r'\s*"?([^"<]+?)"?\s*<', raw or "")
    return (m.group(1) if m else raw or "").strip()


def _text_from_payload(payload: dict[str, Any]) -> str:
    """Plain text of a message: text/plain if present, otherwise text/html stripped of tags."""
    def walk(part: dict[str, Any], mime: str) -> str:
        if part.get("mimeType") == mime and (part.get("body") or {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"] + "===").decode("utf-8", errors="replace")
        for sub in part.get("parts") or []:
            found = walk(sub, mime)
            if found:
                return found
        return ""

    text = walk(payload, "text/plain")
    if not text:
        raw = walk(payload, "text/html")
        text = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)))
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


class GmailConnector(GoogleCalendarConnector):
    api_base = GMAIL_API_BASE

    @property
    def provider(self) -> str:
        return "gmail"

    @property
    def capabilities(self) -> list[str]:
        return ["gmail.search", "gmail.read"]

    def verify(self, auth_metadata: dict[str, Any] | None = None, live_check: bool = False) -> tuple[bool, str]:
        meta = auth_metadata or self.auth_metadata
        if not meta.get("access_token") and not meta.get("refresh_token"):
            return False, "Google authorization missing."
        if not live_check:
            return True, "Gmail authorization present."
        try:
            prof = self._api_request("users/me/profile")
            return True, f"Gmail verified: {prof.get('emailAddress', '')} ({prof.get('messagesTotal', 0)} messages)."
        except Exception as exc:  # noqa: BLE001
            return False, f"Gmail check failed: {exc}"

    def search(self, query: str = "in:inbox", limit: int = 10) -> list[dict[str, Any]]:
        """Newest messages matching a Gmail search (e.g. "is:unread newer_than:2d", "from:rossi"): sender, subject, date, snippet."""
        listing = self._api_request("users/me/messages", params={"q": query or "in:inbox", "maxResults": max(1, min(int(limit), 25))})
        out = []
        for ref in listing.get("messages") or []:
            m = self._api_request(f"users/me/messages/{ref['id']}", params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]})
            hs = (m.get("payload") or {}).get("headers") or []
            out.append({
                "id": m.get("id"), "thread_id": m.get("threadId"), "from": _sender_name(_header(hs, "From")), "from_raw": _header(hs, "From"),
                "subject": _header(hs, "Subject") or "(senza oggetto)", "date": _header(hs, "Date"),
                "internal_ts": int(m.get("internalDate") or 0) // 1000, "snippet": html.unescape(m.get("snippet") or ""),
                "unread": "UNREAD" in (m.get("labelIds") or []),
            })
        return out

    def read(self, message_id: str) -> dict[str, Any]:
        m = self._api_request(f"users/me/messages/{message_id}", params={"format": "full"})
        hs = (m.get("payload") or {}).get("headers") or []
        return {"id": m.get("id"), "from": _header(hs, "From"), "subject": _header(hs, "Subject"), "date": _header(hs, "Date"),
                "text": _text_from_payload(m.get("payload") or {})[:20000]}
