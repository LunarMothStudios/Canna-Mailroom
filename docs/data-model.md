# Data Model

_Last verified against commit `b09c4f1`._

SQLite is the only persisted store in the current implementation. The schema is created lazily by `StateStore._init_db()` in `app/state.py` at startup.

## Persisted Tables

| Table | Primary key | Written by | Read by | Purpose |
|---|---|---|---|---|
| `thread_state` | `thread_id` | worker after successful reply | worker before model call | maps a Gmail thread to the latest OpenAI `response.id` |
| `processed_messages` | `message_id` | worker on skip or completion | worker before processing | deduplicates inbound Gmail messages |
| `dead_letters` | `message_id` | retry wrapper on terminal failure | dead-letter API and worker requeue path | records failed message runs and replay status |
| `outbound_replies` | `message_id` | send idempotency guard | send idempotency guard | records whether a reply was already sent for an inbound message |

## Table Details

### `thread_state`

Purpose: preserve conversation continuity per Gmail thread.

Columns:
- `thread_id TEXT PRIMARY KEY`
- `last_response_id TEXT`
- `updated_at DATETIME DEFAULT CURRENT_TIMESTAMP`

Write behavior:
- upsert via `set_last_response_id(thread_id, response_id)` after a successful reply send path

Read behavior:
- `get_last_response_id(thread_id)` before `EmailAgent.respond_in_thread()`

### `processed_messages`

Purpose: prevent the same inbound Gmail message from being processed twice.

Columns:
- `message_id TEXT PRIMARY KEY`
- `processed_at DATETIME DEFAULT CURRENT_TIMESTAMP`

Write behavior:
- insert via `mark_processed(message_id)` when a message is skipped, completed, or dead-lettered
- delete via `unmark_processed(message_id)` when an operator requeues a dead-letter item

Read behavior:
- `is_processed(message_id)` before worker processing

### `dead_letters`

Purpose: store message runs that exhausted retries or failed with a non-transient error.

Columns:
- `message_id TEXT PRIMARY KEY`
- `thread_id TEXT`
- `from_email TEXT`
- `subject TEXT`
- `error TEXT`
- `attempts INTEGER DEFAULT 1`
- `status TEXT DEFAULT 'dead_letter'`
- `updated_at DATETIME DEFAULT CURRENT_TIMESTAMP`

Write behavior:
- upsert via `upsert_dead_letter(...)` on terminal failure
- update to `requeued` via `mark_dead_letter_requeued(message_id)` when an operator retries a message
- delete via `clear_dead_letter(message_id)` after successful replay

### `outbound_replies`

Purpose: reduce duplicate replies when retries or partial failures occur around the send path.

Columns:
- `message_id TEXT PRIMARY KEY`
- `sent_message_id TEXT`
- `status TEXT DEFAULT 'sent'`
- `source TEXT`
- `updated_at DATETIME DEFAULT CURRENT_TIMESTAMP`

Write behavior:
- upsert via `mark_reply_sent(message_id, sent_message_id, source)` after detecting or sending a reply

Read behavior:
- `has_reply_been_sent(message_id)` before attempting a send

Notes:
- `source` records whether the worker confirmed the reply through the Gmail API send path (`api_send`) or by scanning the thread for an existing reply (`thread_scan`)

## Conceptual Relationships

SQLite does not enforce foreign keys here. The relationships below are conceptual relationships used by the worker logic.

```mermaid
erDiagram
    THREAD_STATE {
        TEXT thread_id PK
        TEXT last_response_id
        DATETIME updated_at
    }

    PROCESSED_MESSAGES {
        TEXT message_id PK
        DATETIME processed_at
    }

    DEAD_LETTERS {
        TEXT message_id PK
        TEXT thread_id
        TEXT from_email
        TEXT subject
        TEXT error
        INTEGER attempts
        TEXT status
        DATETIME updated_at
    }

    OUTBOUND_REPLIES {
        TEXT message_id PK
        TEXT sent_message_id
        TEXT status
        TEXT source
        DATETIME updated_at
    }

    THREAD_STATE ||--o{ DEAD_LETTERS : "same thread_id"
    PROCESSED_MESSAGES ||--o| DEAD_LETTERS : "same message_id"
    PROCESSED_MESSAGES ||--o| OUTBOUND_REPLIES : "same message_id"
```

## Persistence Checkpoints

```mermaid
flowchart LR
    Inbound["Inbound Gmail message"] --> Processed["processed_messages"]
    Inbound --> Dead["dead_letters"]
    Inbound --> Outbound["outbound_replies"]
    Thread["Gmail thread"] --> ThreadState["thread_state"]
    Operator["requeue endpoint"] --> Dead
    Operator --> Processed
```

## Runtime Payload Shapes

### Gmail message payload subset

Read by `app/gmail_worker.py` from `users.messages.get(..., format="full")`:

- `id`
- `threadId`
- `payload.headers[]`
- `payload.body.data`
- `payload.parts[].body.data`

Headers currently consumed:
- `from`
- `subject`
- `message-id`

### AI request payload

Built in `EmailAgent.respond_in_thread()`:

- system prompt text loaded from `SYSTEM_PROMPT.md`
- user content with an `EMAIL CONTEXT` prefix containing `From`, `Subject`, and `Thread-ID`
- optional `previous_response_id`
- tool specification list

### AI tool output payload

Built in the tool loop in `app/ai_agent.py`:

- `type: function_call_output`
- `call_id`
- `output` as a JSON string

## Versioning And Migration Notes

- No migration framework exists yet.
- The application relies on `CREATE TABLE IF NOT EXISTS` during startup.
- The current compatibility model is effectively single-version local deployment.
- Existing databases are forward-filled with newly added tables on startup, as long as schema additions are additive.

Recommended next step:
- introduce explicit schema migrations before adding non-additive changes
