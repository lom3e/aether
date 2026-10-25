"""Gmail: read your mail, and, only after you confirm each change, save reply drafts, move mail to the Trash, archive it
or mark it read. Every change has an exact inverse (delete the draft, take out of the Trash, back to the inbox, unread),
so it can be undone. Mail is never deleted for good. Sending happens only through a confirmed send, which waits a few
seconds (the undo window) before the draft actually leaves.

Built on the Google connector (same token refresh, same revocation handling). Scope: gmail.modify (read, drafts, labels,
Trash; no permanent deletion). Connections made before carried gmail.readonly only: they keep reading, and a change asks
to reconnect. Listing mail does not send its content to any AI model; writing a reply sends the one message being
answered, through the normal (masked, recorded) path.
"""
from __future__ import annotations

import base64
import html
import re
from email.message import EmailMessage
from typing import Any

from aether.connections.google_calendar import GoogleCalendarConnector

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
GMAIL_MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
GMAIL_SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email", GMAIL_MODIFY_SCOPE]
# What each confirmed change does to the labels, and its exact inverse for Undo.
LABEL_OPS = {"archive": ([], ["INBOX"]), "mark_read": ([], ["UNREAD"])}


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
        return ["gmail.search", "gmail.read", "gmail.create_draft", "gmail.trash", "gmail.modify_labels"]

    def can_send(self) -> bool:
        return self.can_change_mail()

    def can_change_mail(self) -> bool:
        """True when this connection was granted gmail.modify (older ones were read-only and must reconnect)."""
        return GMAIL_MODIFY_SCOPE in str(self.auth_metadata.get("scope") or "")

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
            m = self._api_request(f"users/me/messages/{ref['id']}", params={"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date"]})
            hs = (m.get("payload") or {}).get("headers") or []
            out.append({
                "id": m.get("id"), "thread_id": m.get("threadId"), "from": _sender_name(_header(hs, "From")), "from_raw": _header(hs, "From"),
                "to": _header(hs, "To"),
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

    def reply_context(self, message_id: str) -> dict[str, Any]:
        """What a reply needs: who to answer, the subject, the thread and the ids that keep it in the same conversation."""
        m = self._api_request(f"users/me/messages/{message_id}", params={"format": "full"})
        hs = (m.get("payload") or {}).get("headers") or []
        return {"id": m.get("id"), "thread_id": m.get("threadId"), "from_raw": _header(hs, "Reply-To") or _header(hs, "From"),
                "from": _sender_name(_header(hs, "From")), "subject": _header(hs, "Subject"), "message_id_header": _header(hs, "Message-ID"),
                "references": _header(hs, "References"), "date": _header(hs, "Date"), "text": _text_from_payload(m.get("payload") or {})[:12000]}

    def create_draft(self, *, to: str, subject: str, body: str, thread_id: str | None = None, in_reply_to: str = "", references: str = "") -> dict[str, Any]:
        """Saves a draft in Gmail (it is NOT sent). Returns the draft id, used to remove it on Undo."""
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = f"{references} {in_reply_to}".strip()
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        payload: dict[str, Any] = {"message": {"raw": raw}}
        if thread_id:
            payload["message"]["threadId"] = thread_id
        d = self._api_request("users/me/drafts", method="POST", data=payload)
        return {"draft_id": d.get("id"), "message_id": (d.get("message") or {}).get("id"), "thread_id": (d.get("message") or {}).get("threadId")}

    def send_draft(self, draft_id: str) -> dict[str, Any]:
        """Sends a saved draft. Only called after the user confirmed sending and the short undo window passed."""
        sent = self._api_request("users/me/drafts/send", method="POST", data={"id": draft_id})
        return {"message_id": sent.get("id"), "thread_id": sent.get("threadId")}

    def delete_draft(self, draft_id: str) -> None:
        self._api_request(f"users/me/drafts/{draft_id}", method="DELETE")

    def draft_exists(self, draft_id: str) -> bool:
        try:
            self._api_request(f"users/me/drafts/{draft_id}", params={"format": "minimal"})
            return True
        except Exception:  # noqa: BLE001 - gone (sent or deleted by the user)
            return False

    def trash(self, message_ids: list[str]) -> list[str]:
        """Moves messages to the Trash (Gmail empties it after 30 days; nothing is deleted for good here)."""
        done = []
        for mid in message_ids:
            self._api_request(f"users/me/messages/{mid}/trash", method="POST")
            done.append(mid)
        return done

    def untrash(self, message_ids: list[str]) -> list[str]:
        done = []
        for mid in message_ids:
            self._api_request(f"users/me/messages/{mid}/untrash", method="POST")
            done.append(mid)
        return done

    def modify_labels(self, message_ids: list[str], *, add: list[str] | None = None, remove: list[str] | None = None) -> None:
        if message_ids:
            self._api_request("users/me/messages/batchModify", method="POST",
                              data={"ids": list(message_ids), "addLabelIds": list(add or []), "removeLabelIds": list(remove or [])})
