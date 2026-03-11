# Operations Guide

## Runtime behavior

- Worker starts on FastAPI startup.
- Poll interval: `POLL_SECONDS` (default 20s).
- Query used: `is:unread -from:me`.
- Each inbound message is processed once and marked read.

## Session behavior

- Session key = Gmail `threadId`.
- Memory pointer = OpenAI `response.id` stored in SQLite.
- If state DB is removed, thread continuity resets.

## Useful endpoints

- `GET /healthz`
  - service status
  - worker liveness
  - configured poll interval
- `POST /process-now`
  - forces one immediate processing pass

## Logs

Current MVP logs to stdout only:
- `Processed N email(s)` when work occurs

Recommended next:
- add structured JSON logs
- include `thread_id`, `message_id`, and latency

## Recovery playbook

### If replies stop

1. Check process is running (`/healthz`).
2. Verify token validity (rerun OAuth if needed).
3. Verify `.env` values (especially `AGENT_EMAIL`).
4. Send `POST /process-now` and inspect logs.

### If context is wrong

- inspect `state.db` thread mapping
- likely causes:
  - different Gmail thread than expected
  - missing/cleared SQLite state

### If duplicate replies happen

- verify single process instance
- ensure same `state.db` path is used
- do not run multiple workers against same mailbox unless intentionally coordinated

## Safe maintenance tasks

- rotate OpenAI key in `.env`
- rotate Google OAuth token (`token.json`) by reauth flow
- adjust poll interval
- update system prompt file

## Scale notes (post-MVP)

For production-like operation:
- move from polling to Gmail watch + pub/sub
- use Postgres instead of SQLite
- add send approval mode for external recipients
- add sender allowlist
- add retry queue and dead-letter handling
