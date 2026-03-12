# FAQ

_Last verified against commit `b09c4f1`._

## For Stakeholders

### What problem does this project solve?

It demonstrates an email-native AI agent that can hold a threaded conversation over Gmail and use a small set of productivity tools without requiring a separate chat UI.

### What is the main value of this architecture?

It is simple to stand up. A single process can monitor one mailbox, preserve per-thread context, and send useful replies with minimal infrastructure.

### Is it production-ready?

Not yet. It is an MVP with real retry and dead-letter handling, but it lacks approval gates, sender policy controls, and a full automated test suite.

### What are the biggest current boundaries?

- one mailbox
- one active runtime instance
- broad Google OAuth scopes
- no manual approval before outbound send

## For Operators

### Does it check email continuously?

Yes. The worker loops forever and sleeps for `POLL_SECONDS` between cycles. The default is `20`.

### How does it keep conversation context?

It stores the latest OpenAI `response.id` per Gmail `threadId` in the `thread_state` table and passes that value back as `previous_response_id` on the next turn.

### Does it read all of Gmail?

The OAuth scope allows broad Gmail access, but the worker query only asks Gmail for `is:unread -from:me`, then processes the returned messages one by one.

### Can it send mail to arbitrary recipients?

No arbitrary recipient is chosen by the model. The application replies to the sender of the inbound email in the same Gmail thread. There is still no allowlist, so any sender who reaches the mailbox could receive a reply.

### What happens if I delete `state.db`?

You lose:
- thread continuity
- processed-message dedupe history
- dead-letter records
- outbound send-tracking metadata

The app can recreate the schema, but it starts from a cold state.

### What happens if `token.json` expires?

The Google client refreshes automatically when a refresh token is available. If refresh fails, delete `token.json` and rerun `make auth`.

### Why would an email be skipped?

The worker skips messages that are:
- already in `processed_messages`
- sent by the agent itself
- empty after plain-text extraction and reply-cleaning

### Why might `/process-now` return `0` even when mail exists?

Because the candidate messages may all have been skipped, already processed, or dead-lettered during the cycle.

### Can I replay a failed message?

Yes. Use `POST /dead-letter/requeue/{message_id}` and choose whether to process it immediately with `process_now=true` or wait for the next normal poll.

## For Developers

### Does the model have direct Gmail access?

No. Gmail read and send logic lives only in `app/gmail_worker.py`. The model can call only the hardcoded tools exposed in `EmailAgent._tool_specs()`.

### What tools are exposed to the model?

- `research_web`
- `list_drive_files`
- `create_google_doc`
- `append_google_doc`
- `read_google_doc`

### How many tool rounds can happen in one reply?

The tool loop is capped at `6` rounds inside `EmailAgent.respond_in_thread()`.

### Does the app parse HTML-heavy emails or attachments?

Not robustly. The worker is plain-text-first and does not implement attachment handling.

### Does the prompt reload automatically if I edit `SYSTEM_PROMPT.md`?

No. The prompt file is read when `EmailAgent` is constructed at startup. Restart the app after changing it.

### Can I run multiple instances against the same mailbox?

That is not supported safely today. There is no distributed lock or shared coordination mechanism.
