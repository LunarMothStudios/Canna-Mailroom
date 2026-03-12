# Runtime And Pipeline

_Last verified against commit `b6c46e6`._

This document follows the actual message-processing flow implemented in `app/main.py`, `app/gmail_worker.py`, `app/mailbox.py`, and `app/state.py`.

## Stage-By-Stage Execution

| Stage | Code path | Input | Output |
|---|---|---|---|
| 0. Startup | `app.main.startup()` | env vars, prompt file, provider-specific auth material | initialized state store, agent, mailbox provider, and optional watcher or poll thread |
| 1. Ingress | polling or hook path | unread Gmail IDs plus requeued IDs, or `/hooks/gmail` payload | candidate message IDs or `MailboxMessage` objects |
| 2. Snapshot inbound message | `_load_message()` or `process_mailbox_message()` | provider message or hook payload | `inbound_messages` row for retry/replay |
| 3. Early exits and normalization | `clean_reply_text()` | normalized body text | cleaned user input or skip |
| 4. Restore thread context | `StateStore.get_last_response_id()` | thread ID | previous OpenAI response ID or `None` |
| 5. Generate reply | `EmailAgent.respond_in_thread()` | cleaned input, email metadata, previous response ID | final reply text and new response ID |
| 6. Execute model tool loop | `EmailAgent._run_tool()` | function calls emitted by the model | tool outputs fed back into the model |
| 7. Send with idempotency guard | `_send_with_idempotency_guard()` | inbound message ID, reply body, thread metadata | existing sent reply record or new outbound send |
| 8. Finalize success path | provider mark-read plus state writes | message ID and thread ID | message marked processed, thread pointer updated, dead letter cleared |
| 9. Retry or dead-letter | `_process_message_with_retry()` | raised exception | retry with backoff or terminal dead-letter record |

## Ingress Paths

### `google_api` polling mode

```mermaid
flowchart LR
    Gmail["Gmail unread query"] --> Poll["process_once()"]
    Requeue["requeued dead_letters"] --> Poll
    Poll --> Load["GoogleApiMailboxProvider.get_message()"]
    Load --> Worker["EmailThreadWorker"]
```

### `gog` hook mode

```mermaid
flowchart LR
    Gmail["Gmail Pub/Sub event"] --> Gog["gog gmail watch serve"]
    Gog --> Hook["POST /hooks/gmail"]
    Hook --> Parse["MailboxMessage normalization"]
    Parse --> Worker["EmailThreadWorker.process_mailbox_message()"]
```

## Full Run Sequence

```mermaid
sequenceDiagram
    participant Sender as Sender
    participant Ingress as Poll loop or /hooks/gmail
    participant Worker as EmailThreadWorker
    participant DB as StateStore
    participant Agent as EmailAgent
    participant OpenAI as OpenAI API
    participant Mailbox as MailboxProvider

    Sender->>Ingress: send email
    Ingress->>Worker: message id or MailboxMessage
    Worker->>DB: is_processed(message_id)
    DB-->>Worker: false

    alt polling mode
        Worker->>Mailbox: get_message(message_id)
        Mailbox-->>Worker: MailboxMessage
    else hook mode
        Ingress-->>Worker: MailboxMessage already parsed
    end

    Worker->>DB: upsert_inbound_message(message)
    Worker->>DB: get_last_response_id(thread_id)
    DB-->>Worker: response ID or null
    Worker->>Agent: respond_in_thread(...)
    Agent->>OpenAI: responses.create(...)
    OpenAI-->>Agent: response or function calls

    alt model requests tool calls
        Agent->>OpenAI: additional round trips with tool output
        OpenAI-->>Agent: final response
    end

    Agent-->>Worker: reply text and response ID
    Worker->>DB: has_reply_been_sent(message_id)
    alt reply already recorded
        DB-->>Worker: true
    else reply not recorded
        Worker->>Mailbox: find_existing_reply(...)
        alt existing reply found
            Mailbox-->>Worker: existing id
            Worker->>DB: mark_reply_sent(...)
        else no existing reply found
            Mailbox-->>Worker: none
            Worker->>Mailbox: send_reply(...)
            Mailbox-->>Worker: sent id or none
            Worker->>DB: mark_reply_sent(...)
        end
    end

    Worker->>Mailbox: mark_read(message_id)
    Worker->>DB: set_last_response_id(thread_id, response_id)
    Worker->>DB: mark_processed(message_id)
    Worker->>DB: clear_dead_letter(message_id)
    Worker->>DB: delete_inbound_message(message_id)
```

## Candidate Selection And Processing Flow

`process_once()` is only used in `google_api` mode. It merges unread Gmail message IDs with any `requeued` dead-letter IDs so operators can replay a message even if it is no longer unread.

```mermaid
flowchart TD
    Poll["List unread message ids"] --> Merge["Merge with requeued dead-letter ids"]
    Requeue["List requeued dead-letter ids"] --> Merge
    Merge --> Dedupe["Remove duplicates"]
    Dedupe --> Loop["Process each candidate"]
    Loop --> Check{"Already processed?"}
    Check -- Yes --> Skip["Skip message"]
    Check -- No --> Retry["Run retry wrapper"]
    Retry --> Success{"Success?"}
    Success -- Yes --> Count["Increment processed count"]
    Success -- No --> Next["Continue to next message"]
    Skip --> Next
    Count --> Next
```

## Success Path Details

The worker considers a message successfully processed when it:

1. loads or receives a normalized inbound message,
2. gets a final reply from the agent,
3. passes the send idempotency guard,
4. marks the message processed,
5. updates `thread_state`,
6. clears any stale dead-letter row,
7. deletes the `inbound_messages` snapshot.

Messages skipped because they are self-originated or empty are also marked processed, and their inbound snapshot is deleted.

## Retry Logic

Transient failure handling is implemented entirely inside `EmailThreadWorker._process_message_with_retry()`.

- Retry count: `RETRY_MAX_ATTEMPTS`
- Base delay: `RETRY_BASE_DELAY_MS`
- Max delay: `RETRY_MAX_DELAY_MS`
- Jitter: `RETRY_JITTER_MS`

Transient classification sources:
- Google `HttpError` status in `{408, 409, 425, 429, 500, 502, 503, 504}`
- exception attribute `status_code` in the same set
- exception class names containing tokens such as `timeout`, `ratelimit`, `connection`, `temporar`, or `internalserver`

```mermaid
flowchart TD
    Err["Exception raised"] --> Classify{"Transient?"}
    Classify -- Yes --> Attempts{"Attempts remaining?"}
    Attempts -- Yes --> Sleep["Exponential backoff plus jitter"]
    Sleep --> Retry["Retry message"]
    Attempts -- No --> Dead["Write dead_letters row"]
    Classify -- No --> Dead
    Dead --> Mark["mark_processed(message_id)"]
```

## Failure Points And Actual Behavior

| Failure point | Current behavior | Retry? |
|---|---|---|
| Missing or invalid provider setup at startup | app startup fails before worker begins | No |
| Gmail unread list call fails in polling mode | logs and returns zero processed for that cycle | Natural retry on next poll |
| `gog gmail watch start` fails | startup fails in `gog` mode | No |
| `gog gmail watch serve` exits | watcher manager restarts it after 2 seconds | Internal restart |
| invalid `/hooks/gmail` auth token | request is rejected with `401` | Caller must retry with valid token |
| provider message load fails | message run enters retry wrapper | Yes |
| OpenAI Responses API call fails | message run enters retry wrapper | Yes |
| tool argument JSON parsing fails | terminal error and dead-letter | No |
| outbound send fails | message run enters retry wrapper | Yes |
| state write fails during message run | message run fails and usually dead-letters | Partial |

## Explicit Checkpoints

Current checkpointing mechanisms:

- `processed_messages`: inbound message dedupe
- `thread_state`: conversation continuity pointer
- `dead_letters`: failed message tracking and replay queue
- `outbound_replies`: outbound send idempotency tracking
- `inbound_messages`: normalized inbound snapshot for retries and hook replay

Important behaviors:

- Dead-lettered messages are marked processed to avoid infinite retry loops.
- Requeueing a dead-letter row changes its status to `requeued` and removes the processed-message dedupe row.
- Successful replay deletes the dead-letter row and deletes the inbound snapshot.

## Job Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Ingressed
    Ingressed --> Snapshotted
    Snapshotted --> Skipped: self-message or empty text
    Snapshotted --> Generated: reply generation succeeds
    Generated --> Replied: send path succeeds
    Generated --> RetryWait: transient failure
    RetryWait --> Generated: next attempt
    Generated --> DeadLettered: retries exhausted or non-transient failure
    Replied --> Finalized: persist state and clear snapshot
    DeadLettered --> Finalized: persist dead letter and keep snapshot
    Skipped --> Finalized
    Finalized --> [*]
```
