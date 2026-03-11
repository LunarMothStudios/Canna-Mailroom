# FAQ

_Last verified against commit `7317103`._

## Does it check email continuously?
Yes. It polls every `POLL_SECONDS` (default `20`) in `GmailThreadWorker.run_forever`.

## How does it keep conversation context?
Per Gmail `threadId` using `previous_response_id` persisted in SQLite (`thread_state`).

## Does it read all of Gmail?
The OAuth scope currently allows full Gmail access (`https://mail.google.com/`), but worker query only pulls unread non-self messages.

## Can it send emails to anyone?
Currently yes, if it processes a message from that sender. There is no outbound allowlist in code yet.

## What happens if I delete `state.db`?
Thread memory pointers and dedupe history reset. The agent still runs but loses per-thread continuity.

## What if token expires?
Google credentials refresh automatically when refresh token is available; otherwise rerun `make auth`.

## Can I use HTML-heavy emails?
It is plain-text-first. Complex HTML parsing is not implemented yet.

## Can I run this on a server?
Yes, but current docs/implementation are local-first. For server use, add process supervision, managed secrets, and safer outbound controls.

## Does the model have Gmail tool access directly?
No. Gmail interaction is managed in worker code, not exposed as model function tools.

## Why does it skip some emails?
It intentionally skips:
- messages already in `processed_messages`
- self-originated messages (`-from:me` query + sender check)
- messages with empty extracted text
