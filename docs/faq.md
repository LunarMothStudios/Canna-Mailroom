# FAQ

_Last verified against commit `b6c46e6`._

## For Stakeholders

### What problem does this project solve?

It demonstrates an email-native AI agent that can hold a threaded conversation over email and reply from a dedicated mailbox without requiring a separate chat UI.

### What is the main value of this architecture?

It keeps the agent as the main primitive. Email is just the harness around it, so the same core worker and agent can sit behind different mailbox transports.

### Is it production-ready?

Not yet. It has real retries, dead-letter handling, and two ingress modes, but it still lacks approval gates, sender policy controls, and automated behavioral tests.

### What are the biggest current boundaries?

- one mailbox
- one active runtime instance
- no manual approval before outbound send
- Drive and Docs only in `google_api` mode

## For Operators

### Do I need everything we discussed just to see one reply work?

No. The smallest path is `MAIL_PROVIDER=google_api`, one dedicated mailbox, one-time Google auth, then `mailroom run`.

### Why does setup feel large?

Because there are really three separate concerns:
- basic local mailbox testing
- server-style hook ingress
- future product onboarding for user-owned inboxes

The repo supports pieces of all three, but you usually need only one path at a time.

### What is the difference between `google_api` and `gog`?

- `google_api` polls Gmail directly and also enables Drive and Docs tools.
- `gog` uses `gog` for Gmail watch and send, receives messages through `/hooks/gmail`, and is email-only plus `research_web`.

### Why does `gog` still ask for GCP topic information?

Because the current `gog` path uses Gmail watch plus Pub/Sub. End users do not need their own Google Cloud setup, but the deployment still needs one GCP project and topic for the watcher.

### Does `/process-now` always work?

No. It is only supported in `google_api` polling mode. In `gog` mode, use real Gmail hook delivery or test `/hooks/gmail` directly.

### What happens if I delete `state.db`?

You lose:
- thread continuity
- processed-message dedupe history
- dead-letter records
- outbound send-tracking metadata
- cached inbound message snapshots

The app can recreate the schema, but it starts cold.

### Can I replay a failed message?

Yes. Use `POST /dead-letter/requeue/{message_id}`. In `gog` mode, replay depends on a cached `inbound_messages` snapshot because that provider does not refetch by ID.

## For Developers

### Does the model have direct Gmail access?

No. Gmail transport stays application-owned. The model only sees normalized email text and can call the application-defined tool list.

### What tools are exposed to the model?

Always:
- `research_web`

Only in `google_api` mode:
- `list_drive_files`
- `create_google_doc`
- `append_google_doc`
- `read_google_doc`

### Why is there an `inbound_messages` table now?

It keeps a normalized inbound snapshot available for retries, hook processing, and requeue. That is especially important in `gog` mode, where the provider does not refetch by message ID.

### Does the app parse HTML-heavy emails or attachments?

Not robustly. The worker is plain-text-first and does not implement attachment handling.

### Does the prompt reload automatically if I edit `SYSTEM_PROMPT.md`?

No. The prompt file is read when `EmailAgent` is constructed at startup. Restart the app after changing it.

### Can I run multiple instances against the same mailbox?

That is not supported safely today. There is no distributed lock or shared coordination mechanism.
