# Data Model

SQLite is the only persisted store in the current implementation. The schema is created lazily by `StateStore._init_db()` in `app/state.py` at startup.

## Persisted Tables

| Table | Primary key | Written by | Read by | Purpose |
|---|---|---|---|---|
| `thread_state` | `thread_id` | worker after successful reply | worker before model call | maps an email thread to the latest OpenAI `response.id` |
| `processed_messages` | `message_id` | worker on skip, success, or dead-letter | worker before processing | deduplicates inbound messages |
| `dead_letters` | `message_id` | retry wrapper on terminal failure | dead-letter API and replay path | records failed message runs and replay status |
| `outbound_replies` | `message_id` | send idempotency guard | send idempotency guard | records whether a reply was already sent for an inbound message |
| `inbound_messages` | `message_id` | worker before or during processing | worker retry and replay path | stores a normalized inbound message snapshot, including body text |

The current CX provider layer does not persist its own database state. Store knowledge and manual orders are read from JSON files configured in `.env`.

## Runtime Payload Shapes

### Normalized inbound message

Used by `app/mailbox.py` and `app/gmail_worker.py`:

- `message_id`
- `thread_id`
- `from_header`
- `subject`
- `message_id_header`
- `body_text`

### AI request payload

Built in `EmailAgent.respond_in_thread()`:

- system prompt text loaded from `SYSTEM_PROMPT.md`
- user content with an `EMAIL CONTEXT` prefix containing `From`, `Subject`, and `Thread-ID`
- optional `previous_response_id`
- tool specification list from `DispensaryCxToolset.specs()`

### AI tool outputs

Built in the tool loop in `app/ai_agent.py`:

- `type: function_call_output`
- `call_id`
- `output` as a JSON string

The current tool outputs come from two stable function contracts:

- `lookup_order`
- `search_store_knowledge`

### Provider configuration data

Configured through environment variables and local files:

- `STORE_KNOWLEDGE_FILE`
- `MANUAL_ORDER_FILE`
- `ORDER_PROVIDER`
- `ORDER_PROVIDER_FACTORY`
- `DUTCHIE_LOCATION_KEY`
- `DUTCHIE_INTEGRATOR_KEY`
- `DUTCHIE_API_BASE_URL`
- `TREEZ_DISPENSARY`
- `TREEZ_CLIENT_ID`
- `TREEZ_API_KEY`
- `TREEZ_API_BASE_URL`
- `JANE_BRIDGE_URL`
- `JANE_BRIDGE_TOKEN`
- `BRIDGE_ORDER_PROVIDER_URL`
- `BRIDGE_ORDER_PROVIDER_TOKEN`
- `BRIDGE_ORDER_PROVIDER_SOURCE`

## Table Behavior

### `thread_state`

Purpose: preserve conversation continuity per thread.

Columns:

- `thread_id TEXT PRIMARY KEY`
- `last_response_id TEXT`
- `updated_at DATETIME DEFAULT CURRENT_TIMESTAMP`

### `processed_messages`

Purpose: prevent the same inbound message from being processed twice.

Columns:

- `message_id TEXT PRIMARY KEY`
- `processed_at DATETIME DEFAULT CURRENT_TIMESTAMP`

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

### `outbound_replies`

Purpose: reduce duplicate replies when retries or partial failures occur around the send path.

Columns:

- `message_id TEXT PRIMARY KEY`
- `sent_message_id TEXT`
- `status TEXT DEFAULT 'sent'`
- `source TEXT`
- `updated_at DATETIME DEFAULT CURRENT_TIMESTAMP`

`source` records whether the worker confirmed the reply through the direct send path (`api_send`) or by scanning the thread (`thread_scan`).

### `inbound_messages`

Purpose: keep a normalized inbound snapshot available for retries, requeues, and hook-driven processing.

Columns:

- `message_id TEXT PRIMARY KEY`
- `thread_id TEXT NOT NULL`
- `from_header TEXT NOT NULL`
- `subject TEXT NOT NULL`
- `message_id_header TEXT`
- `body_text TEXT NOT NULL`
- `updated_at DATETIME DEFAULT CURRENT_TIMESTAMP`

Lifecycle notes:

- successful runs delete the snapshot
- self-message, sender-policy, and empty-body skips delete the snapshot
- terminal failures can leave the snapshot in place until replay or manual cleanup

## Conceptual Relationships

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

    INBOUND_MESSAGES {
        TEXT message_id PK
        TEXT thread_id
        TEXT from_header
        TEXT subject
        TEXT message_id_header
        TEXT body_text
        DATETIME updated_at
    }

    THREAD_STATE ||--o{ DEAD_LETTERS : "same thread_id"
    THREAD_STATE ||--o{ INBOUND_MESSAGES : "same thread_id"
    PROCESSED_MESSAGES ||--o| DEAD_LETTERS : "same message_id"
    PROCESSED_MESSAGES ||--o| OUTBOUND_REPLIES : "same message_id"
    PROCESSED_MESSAGES ||--o| INBOUND_MESSAGES : "same message_id lifecycle"
    INBOUND_MESSAGES ||--o| DEAD_LETTERS : "same message_id"
```

## Versioning And Migration Notes

- No migration framework exists yet.
- The application relies on `CREATE TABLE IF NOT EXISTS` during startup.
- The compatibility model is effectively single-version local deployment.
- Existing databases are forward-filled with newly added tables on startup, as long as schema additions are additive.
