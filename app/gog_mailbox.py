from __future__ import annotations

import subprocess

from app.mailbox import DeadLetterContext, MailboxMessage


class GogMailboxProvider:
    def __init__(self, account: str):
        self.account = account.strip()

    def list_unread_message_ids(self, limit: int = 20) -> list[str]:
        raise NotImplementedError("gog mailbox uses webhook ingress instead of polling")

    def get_message(self, message_id: str) -> MailboxMessage:
        raise NotImplementedError("gog mailbox does not fetch messages by id in this runtime")

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
        command = [
            "gog",
            "gmail",
            "send",
            "--to",
            to_email,
            "--subject",
            subject if subject.lower().startswith("re:") else f"Re: {subject}",
            "--body-file",
            "-",
        ]
        if self.account:
            command.extend(["--account", self.account])
        if in_reply_to:
            command.extend(["--reply-to-message-id", in_reply_to])

        result = subprocess.run(command, input=body, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            error = (result.stderr or result.stdout or "gog gmail send failed").strip()
            raise RuntimeError(error)

        return None

    def find_existing_reply(
        self,
        *,
        thread_id: str | None,
        from_email: str,
        in_reply_to: str | None,
    ) -> str | None:
        return None

    def mark_read(self, message_id: str) -> None:
        return None

    def get_dead_letter_context(self, message_id: str) -> DeadLetterContext:
        return DeadLetterContext()
