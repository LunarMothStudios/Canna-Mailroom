from __future__ import annotations

import email
import random
import re
import time

from googleapiclient.errors import HttpError

from app.ai_agent import EmailAgent
from app.mailbox import DeadLetterContext, MailboxMessage, MailboxProvider
from app.state import StateStore


def clean_reply_text(text: str) -> str:
    text = re.split(r"\nOn .*wrote:\n", text)[0]
    text = re.split(r"\nFrom: .*\nSent:", text)[0]
    text = re.split(r"\n>+", text)[0]
    return text.strip()


class EmailThreadWorker:
    def __init__(
        self,
        mailbox: MailboxProvider,
        agent_email: str,
        state: StateStore,
        agent: EmailAgent,
        retry_max_attempts: int = 3,
        retry_base_delay_ms: int = 800,
        retry_max_delay_ms: int = 8000,
        retry_jitter_ms: int = 250,
    ):
        self.mailbox = mailbox
        self.agent_email = agent_email.lower().strip()
        self.state = state
        self.agent = agent

        self.retry_max_attempts = max(1, retry_max_attempts)
        self.retry_base_delay_ms = max(1, retry_base_delay_ms)
        self.retry_max_delay_ms = max(self.retry_base_delay_ms, retry_max_delay_ms)
        self.retry_jitter_ms = max(0, retry_jitter_ms)

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

    def _capture_dead_letter_context(self, message_id: str) -> DeadLetterContext:
        try:
            return self.mailbox.get_dead_letter_context(message_id)
        except Exception:
            cached = self.state.get_inbound_message(message_id)
            if not cached:
                return DeadLetterContext()
            return DeadLetterContext(
                thread_id=cached.thread_id,
                from_email=cached.from_header,
                subject=cached.subject,
            )

    def _send_with_idempotency_guard(
        self,
        msg_id: str,
        to_email: str,
        subject: str,
        body: str,
        thread_id: str,
        in_reply_to: str | None,
    ):
        if self.state.has_reply_been_sent(msg_id):
            return

        existing_sent_id = self.mailbox.find_existing_reply(
            thread_id=thread_id,
            from_email=self.agent_email,
            in_reply_to=in_reply_to,
        )
        if existing_sent_id:
            self.state.mark_reply_sent(msg_id, sent_message_id=existing_sent_id, source="thread_scan")
            return

        sent_message_id = self.mailbox.send_reply(
            to_email=to_email,
            subject=subject,
            body=body,
            thread_id=thread_id,
            in_reply_to=in_reply_to,
            from_email=self.agent_email,
        )
        self.state.mark_reply_sent(msg_id, sent_message_id=sent_message_id, source="api_send")

    def _load_message(self, message_id: str) -> MailboxMessage:
        try:
            message = self.mailbox.get_message(message_id)
            self.state.upsert_inbound_message(message)
            return message
        except Exception:
            cached = self.state.get_inbound_message(message_id)
            if cached:
                return cached
            raise

    def _process_loaded_message(self, message: MailboxMessage) -> bool:
        msg_id = message.message_id
        thread_id = message.thread_id
        from_header = message.from_header
        subject = message.subject
        message_id_header = message.message_id_header

        if self.agent_email in from_header.lower():
            self.state.mark_processed(msg_id)
            self.state.delete_inbound_message(msg_id)
            return False

        text = clean_reply_text(message.body_text)
        if not text:
            self.state.mark_processed(msg_id)
            self.state.delete_inbound_message(msg_id)
            return False

        last_resp_id = self.state.get_last_response_id(thread_id)
        reply, new_resp_id = self.agent.respond_in_thread(
            user_input=text,
            thread_id=thread_id,
            last_response_id=last_resp_id,
            email_metadata={"from": from_header, "subject": subject},
        )

        self._send_with_idempotency_guard(
            msg_id=msg_id,
            to_email=email.utils.parseaddr(from_header)[1] or from_header,
            subject=subject,
            body=reply,
            thread_id=thread_id,
            in_reply_to=message_id_header,
        )

        self.mailbox.mark_read(msg_id)

        self.state.set_last_response_id(thread_id, new_resp_id)
        self.state.mark_processed(msg_id)
        self.state.clear_dead_letter(msg_id)
        self.state.delete_inbound_message(msg_id)
        return True

    def _process_message_with_retry(self, msg_id: str, message: MailboxMessage | None = None) -> bool:
        last_err: Exception | None = None
        cached_message = message
        if cached_message:
            self.state.upsert_inbound_message(cached_message)

        for attempt in range(1, self.retry_max_attempts + 1):
            try:
                loaded_message = cached_message or self._load_message(msg_id)
                return self._process_loaded_message(loaded_message)
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
                    thread_id=context.thread_id,
                    from_email=context.from_email,
                    subject=context.subject,
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
                thread_id=context.thread_id,
                from_email=context.from_email,
                subject=context.subject,
                status="dead_letter",
            )
            self.state.mark_processed(msg_id)
        return False

    def process_message_by_id(self, message_id: str) -> bool:
        if self.state.is_processed(message_id):
            return False
        return self._process_message_with_retry(message_id)

    def process_mailbox_message(self, message: MailboxMessage) -> bool:
        if self.state.is_processed(message.message_id):
            return False
        return self._process_message_with_retry(message.message_id, message=message)

    def requeue_dead_letter(self, message_id: str, process_immediately: bool = False) -> bool:
        self.state.mark_dead_letter_requeued(message_id)
        self.state.unmark_processed(message_id)

        if process_immediately:
            return self.process_message_by_id(message_id)

        return True

    def process_once(self) -> int:
        unread_ids: list[str] = []

        try:
            unread_ids = self.mailbox.list_unread_message_ids(limit=20)
        except Exception as err:
            print(f"Failed to list unread messages: {err.__class__.__name__}: {err}")

        # Requeued dead-letters must be processable even when no longer unread.
        requeued_ids = self.state.list_requeued_message_ids(limit=20)

        candidate_ids: list[str] = []
        seen: set[str] = set()
        for msg_id in requeued_ids + unread_ids:
            if msg_id in seen:
                continue
            seen.add(msg_id)
            candidate_ids.append(msg_id)

        processed_count = 0

        for msg_id in candidate_ids:
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


GmailThreadWorker = EmailThreadWorker
