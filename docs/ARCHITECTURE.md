# Architecture

## Goal

Canna Mailroom is an email-native AI worker that turns Gmail threads into persistent AI sessions.

A human emails the agent mailbox, and the system:
1. reads new unread inbound emails,
2. maps each email to a Gmail `threadId`,
3. restores AI context for that thread,
4. generates a response (with optional Drive/Docs tool use),
5. replies in the same thread,
6. stores updated session pointer.

---

## Components

- `app/main.py`
  - FastAPI bootstrapping
  - Initializes Google API clients, OpenAI agent, state store
  - Starts background polling worker thread

- `app/gmail_worker.py`
  - Polls Gmail (`is:unread -from:me`)
  - Extracts plain text, strips quoted chain, deduplicates by message id
  - Calls AI agent and sends in-thread reply

- `app/ai_agent.py`
  - Wrapper around OpenAI Responses API
  - Uses `previous_response_id` as thread memory pointer
  - Supports tool calling loop for Drive/Docs operations

- `app/tools.py`
  - Drive + Docs tool implementations:
    - `list_drive_files`
    - `create_google_doc`
    - `append_google_doc`
    - `read_google_doc`

- `app/google_clients.py`
  - OAuth token bootstrap/refresh
  - Creates Gmail / Drive / Docs service clients

- `app/state.py`
  - SQLite persistence
  - `thread_state`: maps `thread_id -> last_response_id`
  - `processed_messages`: dedupe guard

---

## Thread-as-Session Model

Session continuity is handled by:
- Gmail `threadId` as session key
- OpenAI `response.id` chain via `previous_response_id`

This yields stateful conversation per email thread while keeping separate threads isolated.

---

## Data Flow

1. Worker queries Gmail unread messages.
2. For each message:
   - skip if already processed
   - parse headers/body
   - skip if sender is the agent itself
3. Resolve `thread_id` and fetch `last_response_id` from SQLite.
4. Send cleaned body + metadata to OpenAI.
5. Handle function calls (Drive/Docs), returning tool outputs.
6. Receive final assistant response.
7. Send Gmail reply with same `threadId`.
8. Mark original message read + processed.
9. Update `thread_state.last_response_id`.

---

## Trust Boundaries

- Gmail / Google Workspace APIs: external side effects (email send, docs writes)
- OpenAI API: model reasoning + tool-call planning
- Local SQLite: minimal local state (thread pointers + dedupe)

No business data store beyond Gmail + docs is included in this MVP.

---

## Current Constraints

- Polling model (no Gmail push/webhooks yet)
- Plain-text-first parsing (HTML handling is minimal)
- No per-sender allowlist/denylist yet
- No explicit approval gate before outbound send
- Single mailbox worker process

These are acceptable for local MVP validation and should be hardened before broader deployment.
