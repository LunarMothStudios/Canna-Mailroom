# ADR-006: Track Outbound Replies Per Inbound Message

- Status: Accepted
- Date: 2026-03-11
- Last verified against commit `b6c46e6`

## Context

The worker can fail after generating a reply but before all local state is durably updated. Retrying blindly would risk sending duplicate emails to the user, which is highly visible and difficult to undo.

## Decision

Track outbound reply state per inbound Gmail message in `outbound_replies`. Before sending, the worker:

1. checks whether that inbound message was already marked as sent in SQLite
2. scans the Gmail thread for an existing agent-authored reply with the same `In-Reply-To`
3. sends only if neither check confirms a prior reply

## Consequences

Positive:
- reduces duplicate replies caused by retries or partial failures
- provides a recovery path when Gmail send succeeded but local state was incomplete

Negative:
- still best-effort, not globally coordinated
- if thread scanning fails and local state is missing, the worker may still resend

## Evidence In Code

- `app/state.py` defines `outbound_replies`, `mark_reply_sent()`, and `has_reply_been_sent()`
- `app/gmail_worker.py` defines `_send_with_idempotency_guard()` and `_find_existing_sent_reply()`
