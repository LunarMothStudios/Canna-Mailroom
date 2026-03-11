# Runtime and Pipeline

_Last verified against commit `7317103`._

## Stage-by-stage execution

| Stage | Module | Input | Output |
|---|---|---|---|
| 0. Startup | `app/main.py` | env + files | initialized worker and clients |
| 1. Poll | `GmailThreadWorker.process_once` | Gmail query | list of unread messages |
| 2. Fetch detail | `gmail.users.messages.get` | message id | full message payload |
| 3. Normalize | `extract_plain_text`, `clean_reply_text` | Gmail payload | cleaned user text |
| 4. Restore context | `StateStore.get_last_response_id` | thread_id | prior response id or null |
| 5. Generate | `EmailAgent.respond_in_thread` | text + previous_response_id | response text + new response id |
| 6. Tool calls (optional) | `EmailAgent._run_tool` | model function calls | function_call_output payloads |
| 7. Send reply | `_send_reply` | to/subject/body/thread | Gmail sent message |
| 8. Mark processed | `modify UNREAD`, state methods | msg/thread IDs | deduped, thread pointer updated |

## Full run sequence

```mermaid
sequenceDiagram
    participant S as Sender
    participant G as Gmail API
    participant W as GmailThreadWorker
    participant DB as SQLite StateStore
    participant A as EmailAgent
    participant O as OpenAI API
    participant T as Workspace Tools

    S->>G: Sends email
    W->>G: list unread (is:unread -from:me)
    G-->>W: message ids
    W->>G: get full message
    G-->>W: payload + threadId
    W->>DB: is_processed(message_id)?
    DB-->>W: false
    W->>DB: get_last_response_id(threadId)
    DB-->>W: response id / null
    W->>A: respond_in_thread(text, threadId, prev)
    A->>O: responses.create(...)
    O-->>A: response or function_call

    alt function calls present
      A->>T: run tool(s)
      T-->>A: tool output JSON
      A->>O: responses.create(previous_response_id=response.id, tool output)
      O-->>A: final response
    end

    A-->>W: final text + new response_id
    W->>G: send reply in same thread
    W->>G: remove UNREAD label
    W->>DB: set_last_response_id(threadId,new_id)
    W->>DB: mark_processed(message_id)
```

## Pipeline flow and checkpoints

```mermaid
flowchart TD
    A[Poll unread] --> B{Any messages?}
    B -- No --> Z[Sleep POLL_SECONDS]
    B -- Yes --> C[Fetch message detail]
    C --> D{Already processed?}
    D -- Yes --> N[Skip]
    D -- No --> E[Extract + clean text]
    E --> F{Text empty?}
    F -- Yes --> M[Mark processed + skip]
    F -- No --> G[Load thread context]
    G --> H[Call OpenAI + tools]
    H --> I[Send reply]
    I --> J[Mark read]
    J --> K[Persist state]
    K --> L[Increment processed count]
    N --> B
    M --> B
    L --> B
    Z --> A
```

## Failure points and current behavior

| Failure point | Current behavior | Retry strategy present? |
|---|---|---|
| Google OAuth missing/invalid at startup | startup fails | No explicit retry |
| Gmail list/get/send API error | exception bubbles and can break worker loop call | No |
| OpenAI API error | exception bubbles | No |
| Tool call arg parse (`json.loads`) error | exception bubbles | No |
| SQLite transient error | exception bubbles | No |

## Checkpoints

Current explicit checkpoints:
- message-level dedupe via `processed_messages`
- thread memory pointer via `thread_state`

No queue checkpoints and no dead-letter handling exist yet.

## Job lifecycle (message-level)

```mermaid
stateDiagram-v2
    [*] --> Discovered
    Discovered --> Skipped: already processed or self-message
    Discovered --> Parsed
    Parsed --> Skipped: empty body
    Parsed --> Generated
    Generated --> Replied
    Replied --> Finalized
    Finalized --> [*]
```
