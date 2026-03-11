from __future__ import annotations

import base64
import email
from email.mime.text import MIMEText
import re
import time
from typing import Any

from app.ai_agent import EmailAgent
from app.state import StateStore


def _decode_b64url(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
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


def clean_reply_text(text: str) -> str:
    text = re.split(r"\nOn .*wrote:\n", text)[0]
    text = re.split(r"\nFrom: .*\nSent:", text)[0]
    text = re.split(r"\n>+", text)[0]
    return text.strip()


class GmailThreadWorker:
    def __init__(self, gmail_service, agent_email: str, state: StateStore, agent: EmailAgent):
        self.gmail = gmail_service
        self.agent_email = agent_email.lower().strip()
        self.state = state
        self.agent = agent

    def _message_headers(self, headers: list[dict[str, str]]) -> dict[str, str]:
        out = {}
        for h in headers:
            out[h.get("name", "").lower()] = h.get("value", "")
        return out

    def _send_reply(self, to_email: str, subject: str, body: str, thread_id: str, in_reply_to: str | None):
        msg = MIMEText(body)
        msg["to"] = to_email
        msg["from"] = self.agent_email
        msg["subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        self.gmail.users().messages().send(
            userId="me",
            body={"raw": raw, "threadId": thread_id},
        ).execute()

    def process_once(self) -> int:
        q = "is:unread -from:me"
        msgs = (
            self.gmail.users()
            .messages()
            .list(userId="me", q=q, maxResults=20)
            .execute()
            .get("messages", [])
        )

        processed_count = 0

        for msg_ref in msgs:
            msg_id = msg_ref["id"]
            if self.state.is_processed(msg_id):
                continue

            full = (
                self.gmail.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )

            payload = full.get("payload", {})
            headers = self._message_headers(payload.get("headers", []))
            thread_id = full.get("threadId")
            from_header = headers.get("from", "")
            subject = headers.get("subject", "(no subject)")
            message_id_header = headers.get("message-id")

            if self.agent_email in from_header.lower():
                self.state.mark_processed(msg_id)
                continue

            text = clean_reply_text(extract_plain_text(payload))
            if not text:
                self.state.mark_processed(msg_id)
                continue

            last_resp_id = self.state.get_last_response_id(thread_id)
            reply, new_resp_id = self.agent.respond_in_thread(
                user_input=text,
                thread_id=thread_id,
                last_response_id=last_resp_id,
                email_metadata={"from": from_header, "subject": subject},
            )

            self._send_reply(
                to_email=email.utils.parseaddr(from_header)[1] or from_header,
                subject=subject,
                body=reply,
                thread_id=thread_id,
                in_reply_to=message_id_header,
            )

            self.gmail.users().messages().modify(
                userId="me",
                id=msg_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()

            self.state.set_last_response_id(thread_id, new_resp_id)
            self.state.mark_processed(msg_id)
            processed_count += 1

        return processed_count

    def run_forever(self, poll_seconds: int = 20):
        while True:
            count = self.process_once()
            if count:
                print(f"Processed {count} email(s)")
            time.sleep(poll_seconds)
