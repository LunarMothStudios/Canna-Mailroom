from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MailboxMessage:
    message_id: str
    thread_id: str
    from_header: str
    subject: str
    message_id_header: str | None
    body_text: str


@dataclass(frozen=True)
class DeadLetterContext:
    thread_id: str | None = None
    from_email: str | None = None
    subject: str | None = None


class MailboxProvider(Protocol):
    def list_unread_message_ids(self, limit: int = 20) -> list[str]:
        ...

    def get_message(self, message_id: str) -> MailboxMessage:
        ...

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
        ...

    def find_existing_reply(
        self,
        *,
        thread_id: str | None,
        from_email: str,
        in_reply_to: str | None,
    ) -> str | None:
        ...

    def mark_read(self, message_id: str) -> None:
        ...

    def get_dead_letter_context(self, message_id: str) -> DeadLetterContext:
        ...
