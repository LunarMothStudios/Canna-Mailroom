from __future__ import annotations

import base64
import email
from email.mime.text import MIMEText
import random
import re
import time
from typing import Any

from googleapiclient.errors import HttpError

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
    def __init__(
        self,
        gmail_service,
        agent_email: str,
        state: StateStore,
        agent: EmailAgent,
        retry_max_attempts: int = 3,
        retry_base_delay_ms: int = 800,
        retry_max_delay_ms: int = 8000,
        retry_jitter_ms: int = 250,
    ):
        self.gmail = gmail_service
        self.agent_email = agent_email.lower().strip()
        self.state = state
        self.agent = agent

        self.retry_max_attempts = max(1, retry_max_attempts)
        self.retry_base_delay_ms = max(1, retry_base_delay_ms)
        self.retry_max_delay_ms = max(self.retry_base_delay_ms, retry_max_delay_ms)
        self.retry_jitter_ms = max(0, retry_jitter_ms)

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

    def _is_transient_error(self, err: Exception) -> bool:
        if isinstance(err, HttpError):
            status = getattr(getattr(err, "resp", None), "status", None)
            return status in {408, 409, 425, 429, 500, 502, 503, 504}

        status_code = getattr(err, "status_code", None)
        if status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
            return True

        name = err.__class__.__name__.lower()
        return any(token in name for token in ["timeout", "ratelimit", "connection", "temporar", "internalserver"])

    def _retry_delay_seconds(self, attempt: int) -> float:
        # attempt is 1-indexed
        exp_ms = self.retry_base_delay_ms * (2 ** max(0, attempt - 1))
        capped_ms = min(self.retry_max_delay_ms, exp_ms)
        jitter_ms = random.randint(0, self.retry_jitter_ms) if self.retry_jitter_ms > 0 else 0
        return (capped_ms + jitter_ms) / 1000.0

    def _capture_dead_letter_context(self, message_id: str) -> dict[str, str | None]:
        try:
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
            return {
                "thread_id": meta.get("threadId"),
                "from_email": headers.get("from"),
                "subject": headers.get("subject"),
            }
        except Exception:
            return {"thread_id": None, "from_email": None, "subject": None}

    def _process_message_once(self, msg_id: str) -> bool:
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
            return False

        text = clean_reply_text(extract_plain_text(payload))
        if not text:
            self.state.mark_processed(msg_id)
            return False

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
        self.state.clear_dead_letter(msg_id)
        return True

    def _process_message_with_retry(self, msg_id: str) -> bool:
        last_err: Exception | None = None

        for attempt in range(1, self.retry_max_attempts + 1):
            try:
                return self._process_message_once(msg_id)
            except Exception as err:
                last_err = err
                transient = self._is_transient_error(err)
                should_retry = transient and attempt < self.retry_max_attempts

                if should_retry:
                    delay = self._retry_delay_seconds(attempt)
                    print(
                        f"Retrying message {msg_id}: attempt {attempt}/{self.retry_max_attempts} failed "
                        f"with {err.__class__.__name__}: {err}. Backing off {delay:.2f}s"
                    )
                    time.sleep(delay)
                    continue

                context = self._capture_dead_letter_context(msg_id)
                self.state.upsert_dead_letter(
                    message_id=msg_id,
                    error=f"{err.__class__.__name__}: {err}",
                    attempts=attempt,
                    thread_id=context.get("thread_id"),
                    from_email=context.get("from_email"),
                    subject=context.get("subject"),
                    status="dead_letter",
                )
                self.state.mark_processed(msg_id)
                print(
                    f"Moved message {msg_id} to dead-letter after {attempt} attempt(s): "
                    f"{err.__class__.__name__}: {err}"
                )
                return False

        # Defensive fallback; should never hit due loop return above.
        if last_err is not None:
            context = self._capture_dead_letter_context(msg_id)
            self.state.upsert_dead_letter(
                message_id=msg_id,
                error=f"{last_err.__class__.__name__}: {last_err}",
                attempts=self.retry_max_attempts,
                thread_id=context.get("thread_id"),
                from_email=context.get("from_email"),
                subject=context.get("subject"),
                status="dead_letter",
            )
            self.state.mark_processed(msg_id)
        return False

    def requeue_dead_letter(self, message_id: str):
        self.state.mark_dead_letter_requeued(message_id)
        self.state.unmark_processed(message_id)

    def process_once(self) -> int:
        q = "is:unread -from:me"
        try:
            msgs = (
                self.gmail.users()
                .messages()
                .list(userId="me", q=q, maxResults=20)
                .execute()
                .get("messages", [])
            )
        except Exception as err:
            print(f"Failed to list unread messages: {err.__class__.__name__}: {err}")
            return 0

        processed_count = 0

        for msg_ref in msgs:
            msg_id = msg_ref["id"]
            if self.state.is_processed(msg_id):
                continue

            if self._process_message_with_retry(msg_id):
                processed_count += 1

        return processed_count

    def run_forever(self, poll_seconds: int = 20):
        while True:
            try:
                count = self.process_once()
                if count:
                    print(f"Processed {count} email(s)")
            except Exception as err:
                print(f"Worker loop error: {err.__class__.__name__}: {err}")
            time.sleep(poll_seconds)
