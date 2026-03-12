from __future__ import annotations

import base64
from email.mime.text import MIMEText
from typing import Any

from app.mailbox import DeadLetterContext, MailboxMessage


def _decode_b64url(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def extract_plain_text(payload: dict[str, Any]) -> str:
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain" and payload.get("body", {}).get("data"):
        return _decode_b64url(payload["body"]["data"]).decode("utf-8", errors="ignore")

    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return _decode_b64url(part["body"]["data"]).decode("utf-8", errors="ignore")

    if payload.get("body", {}).get("data"):
        return _decode_b64url(payload["body"]["data"]).decode("utf-8", errors="ignore")

    return ""


class GoogleApiMailboxProvider:
    def __init__(self, gmail_service):
        self.gmail = gmail_service

    def _message_headers(self, headers: list[dict[str, str]]) -> dict[str, str]:
        out: dict[str, str] = {}
        for header in headers:
            out[header.get("name", "").lower()] = header.get("value", "")
        return out

    def list_unread_message_ids(self, limit: int = 20) -> list[str]:
        query = "is:unread -from:me"
        response = (
            self.gmail.users()
            .messages()
            .list(userId="me", q=query, maxResults=limit)
            .execute()
        )
        return [message["id"] for message in response.get("messages", [])]

    def get_message(self, message_id: str) -> MailboxMessage:
        full = (
            self.gmail.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        payload = full.get("payload", {})
        headers = self._message_headers(payload.get("headers", []))
        return MailboxMessage(
            message_id=message_id,
            thread_id=full.get("threadId", ""),
            from_header=headers.get("from", ""),
            subject=headers.get("subject", "(no subject)"),
            message_id_header=headers.get("message-id"),
            body_text=extract_plain_text(payload),
        )

    def send_reply(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        thread_id: str,
        in_reply_to: str | None,
        from_email: str,
    ) -> str | None:
        message = MIMEText(body)
        message["to"] = to_email
        message["from"] = from_email
        message["subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
            message["References"] = in_reply_to

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        response = (
            self.gmail.users()
            .messages()
            .send(userId="me", body={"raw": raw, "threadId": thread_id})
            .execute()
        )
        return response.get("id")

    def find_existing_reply(
        self,
        *,
        thread_id: str | None,
        from_email: str,
        in_reply_to: str | None,
    ) -> str | None:
        if not thread_id or not in_reply_to:
            return None

        try:
            thread = (
                self.gmail.users()
                .threads()
                .get(
                    userId="me",
                    id=thread_id,
                    format="metadata",
                    metadataHeaders=["From", "In-Reply-To"],
                )
                .execute()
            )
        except Exception:
            return None

        target = in_reply_to.strip()
        lower_from_email = from_email.lower().strip()
        for message in thread.get("messages", []):
            payload = message.get("payload", {})
            headers = self._message_headers(payload.get("headers", []))
            from_header = headers.get("from", "").lower()
            in_reply_header = headers.get("in-reply-to", "").strip()
            if lower_from_email in from_header and in_reply_header == target:
                return message.get("id")

        return None

    def mark_read(self, message_id: str) -> None:
        self.gmail.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()

    def get_dead_letter_context(self, message_id: str) -> DeadLetterContext:
        meta = (
            self.gmail.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["From", "Subject"],
            )
            .execute()
        )
        payload = meta.get("payload", {})
        headers = self._message_headers(payload.get("headers", []))
        return DeadLetterContext(
            thread_id=meta.get("threadId"),
            from_email=headers.get("from"),
            subject=headers.get("subject"),
        )
