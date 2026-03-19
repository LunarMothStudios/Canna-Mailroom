from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app.cx_models import ProviderAPIError
from app.gmail_worker import EmailThreadWorker, clean_reply_text
from app.mailbox import MailboxMessage


def make_message(*, from_header: str = "Human <human@example.com>", body: str = "Hello there") -> MailboxMessage:
    return MailboxMessage(
        message_id="msg-1",
        thread_id="thread-1",
        from_header=from_header,
        subject="Need help",
        message_id_header="<msg-1@example.com>",
        body_text=body,
    )


class GmailWorkerTests(unittest.TestCase):
    def make_worker(self, *, allowed_senders=(), sender_policy_mode="all"):
        mailbox = Mock()
        state = Mock()
        agent = Mock()
        state.is_processed.return_value = False
        state.has_reply_been_sent.return_value = False
        state.get_last_response_id.return_value = "prev-response"
        mailbox.find_existing_reply.return_value = None
        mailbox.send_reply.return_value = "sent-1"
        agent.respond_in_thread.return_value = ("Reply body", "new-response")
        worker = EmailThreadWorker(
            mailbox=mailbox,
            agent_email="agent@example.com",
            state=state,
            agent=agent,
            sender_policy_mode=sender_policy_mode,
            allowed_senders=allowed_senders,
        )
        return worker, mailbox, state, agent

    def test_clean_reply_text_strips_quoted_content(self):
        cleaned = clean_reply_text("Thanks\nOn Tue wrote:\nOlder text\n> quoted")
        self.assertEqual(cleaned, "Thanks")

    def test_self_messages_are_skipped(self):
        worker, mailbox, state, agent = self.make_worker()

        result = worker._process_loaded_message(make_message(from_header="Agent <agent@example.com>"))

        self.assertFalse(result)
        state.mark_processed.assert_called_once_with("msg-1")
        state.delete_inbound_message.assert_called_once_with("msg-1")
        agent.respond_in_thread.assert_not_called()
        mailbox.send_reply.assert_not_called()

    def test_sender_outside_allowlist_is_marked_read_and_skipped(self):
        worker, mailbox, state, agent = self.make_worker(
            sender_policy_mode="allowlist",
            allowed_senders=("friend@example.com",),
        )

        result = worker._process_loaded_message(make_message())

        self.assertFalse(result)
        mailbox.mark_read.assert_called_once_with("msg-1")
        state.mark_processed.assert_called_once_with("msg-1")
        agent.respond_in_thread.assert_not_called()

    def test_happy_path_sends_reply_and_updates_state(self):
        worker, mailbox, state, agent = self.make_worker()

        result = worker._process_loaded_message(make_message())

        self.assertTrue(result)
        agent.respond_in_thread.assert_called_once()
        mailbox.send_reply.assert_called_once()
        mailbox.mark_read.assert_called_once_with("msg-1")
        state.set_last_response_id.assert_called_once_with("thread-1", "new-response")
        state.mark_reply_sent.assert_called_once_with("msg-1", sent_message_id="sent-1", source="api_send")
        state.clear_dead_letter.assert_called_once_with("msg-1")
        state.delete_inbound_message.assert_called_once_with("msg-1")

    def test_existing_reply_prevents_duplicate_send(self):
        worker, mailbox, state, agent = self.make_worker()
        mailbox.find_existing_reply.return_value = "existing-sent"

        result = worker._process_loaded_message(make_message())

        self.assertTrue(result)
        mailbox.send_reply.assert_not_called()
        state.mark_reply_sent.assert_called_once_with("msg-1", sent_message_id="existing-sent", source="thread_scan")

    def test_transient_failure_retries_then_succeeds(self):
        worker, mailbox, state, agent = self.make_worker()
        agent.respond_in_thread.side_effect = [
            ProviderAPIError("slow down", status_code=429),
            ("Reply body", "new-response"),
        ]

        with patch("app.gmail_worker.time.sleep") as sleep_mock:
            result = worker.process_mailbox_message(make_message())

        self.assertTrue(result)
        self.assertEqual(agent.respond_in_thread.call_count, 2)
        sleep_mock.assert_called_once()
        state.upsert_dead_letter.assert_not_called()

    def test_non_transient_failure_dead_letters_message(self):
        worker, mailbox, state, agent = self.make_worker()
        agent.respond_in_thread.side_effect = ProviderAPIError("unauthorized", status_code=401)
        mailbox.get_dead_letter_context.return_value = Mock(
            thread_id="thread-1",
            from_email="human@example.com",
            subject="Need help",
        )

        result = worker.process_mailbox_message(make_message())

        self.assertFalse(result)
        state.upsert_dead_letter.assert_called_once()
        mailbox.send_reply.assert_not_called()
