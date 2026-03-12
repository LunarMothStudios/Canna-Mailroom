# ADR-002: Use A Polling Worker Instead Of Gmail Push

- Status: Accepted
- Date: 2026-03-11
- Last verified against commit `b09c4f1`

## Context

The project is optimized for a local-first MVP. Adding Gmail push delivery would require extra infrastructure and coordination that the current product scope does not need.

## Decision

Run a background thread inside the FastAPI process. Poll Gmail every `POLL_SECONDS` using the query `is:unread -from:me`.

## Consequences

Positive:
- simple bring-up on a laptop or single host
- no webhook, Pub/Sub, or external queue dependency
- easy to force a cycle through `/process-now`

Negative:
- replies are delayed by the polling interval
- Gmail is queried continuously even when the inbox is idle
- multiple active instances against one mailbox are unsafe

## Evidence In Code

- `app/main.py` starts `worker.run_forever()` in a daemon thread
- `app/gmail_worker.py` implements `run_forever()` and `process_once()`
