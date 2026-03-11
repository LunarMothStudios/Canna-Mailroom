# ADR-002: Use Polling Worker Instead of Gmail Push

- Status: Accepted
- Date: 2026-03-11
- Last verified against commit `7317103`

## Context
Need a fast local MVP without webhook/pubsub infrastructure.

## Decision
Run a background thread that polls Gmail every `POLL_SECONDS` using query `is:unread -from:me`.

## Consequences
### Positive
- simple local setup
- no external queue/pubsub dependency

### Negative
- introduces polling latency
- less efficient than push notifications
- duplicate processing risks if multiple workers run against same mailbox

## Evidence in code
- `app/main.py` (daemon thread startup)
- `app/gmail_worker.py` (`run_forever`, `process_once`, query string)
