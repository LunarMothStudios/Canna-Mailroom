# Security And Safety

This document describes the security posture of the current codebase.

## Secrets And Auth Model

| Asset | Source | Used by | Risk if compromised |
|---|---|---|---|
| `OPENAI_API_KEY` | `.env` | `app/ai_agent.py` | model access and billable API usage |
| `credentials.json` | local file | `app/google_clients.py` | Gmail OAuth bootstrap in `google_api` mode |
| `token.json` | local file | `app/google_clients.py` | ongoing Gmail access in `google_api` mode |
| `DUTCHIE_LOCATION_KEY` / `DUTCHIE_INTEGRATOR_KEY` | `.env` | `app/cx_providers.py` | third-party order lookup access |
| `TREEZ_CLIENT_ID` / `TREEZ_API_KEY` | `.env` | `app/cx_providers.py` | third-party order lookup access |
| `JANE_BRIDGE_TOKEN` | `.env` | `app/cx_providers.py` | access to the merchant-operated Jane bridge |
| `BRIDGE_ORDER_PROVIDER_TOKEN` | `.env` | `app/cx_providers.py` | access to a generic bridge-backed order service |
| `GOG_GMAIL_HOOK_TOKEN` | `.env` | `app/main.py` | unauthorized callers could inject fake hook events |
| `GOG_GMAIL_PUSH_TOKEN` | `.env` | `app/gog_watcher.py` | unauthorized callers could reach the local `gog` watch endpoint |
| `state.db` | local file | `app/state.py`, `app/gmail_worker.py` | thread pointers, message metadata, dead-letter details, cached message bodies |
| `SYSTEM_PROMPT.md` | local file | `app/ai_agent.py` | changes model behavior on restart |

Current Google scope in Mailroom itself:

- `https://mail.google.com/`

## What The Model Can And Cannot Control

| Concern | Controlled by | Notes |
|---|---|---|
| recipient address | application | parsed from the inbound `From` header |
| reply thread | application | set from the inbound thread ID |
| reply body | model | generated through `EmailAgent.respond_in_thread()` |
| tool calls | model within application-defined limits | limited to two explicit functions |
| Gmail reads and sends | application or external `gog` transport | the model has no direct Gmail tool |

This means the model cannot browse the inbox or choose arbitrary recipients, but it can decide the final text sent to the original sender.

## Current Approval Model

There is no manual approval gate.

Current safeguards before send:

- self-message skip
- empty-body skip
- optional sender allowlist
- inbound dedupe via `processed_messages`
- outbound dedupe via `outbound_replies`
- best-effort thread scan in `google_api` mode

Missing safeguards:

- human approval before send
- denylist support
- outbound content filtering
- rate limiting
- per-sender policy rules

## Data Handling Rules

### Data sent to OpenAI

- cleaned email body text
- `From`
- `Subject`
- thread ID
- previous OpenAI `response.id` chain
- tool outputs from `lookup_order` and `search_store_knowledge`

### Data stored locally

- thread IDs
- OpenAI response IDs
- inbound message IDs
- dead-letter metadata such as sender, subject, error, attempts
- outbound sent-message tracking metadata
- cached inbound message snapshots in `inbound_messages`

### Data sent to providers

- `search_store_knowledge` reads local JSON only
- `lookup_order` may send order number and verification data to the configured order provider
- the built-in Dutchie adapter may send sender email to Dutchie for best-effort customer verification
- the built-in Treez adapter signs each request with the configured private key and may send sender verification hints when the caller provides them
- bridge-backed Jane or generic bridge providers send order identifiers and optional verification hints to the configured bridge URL

## Safe Defaults For Local Use

- use a dedicated mailbox
- prefer `SENDER_POLICY_MODE=allowlist` during early testing
- keep `.env`, `state.db`, and prompt files out of git
- keep `credentials.json` and `token.json` out of git in `google_api` mode
- avoid sensitive or regulated inboxes until you are comfortable with the guardrails
- run only one active instance against the mailbox

## Known Gaps

- no manual approval gate
- no DLP or PII redaction layer
- sender policy is limited to a simple email allowlist
- cached inbound body text can persist in SQLite after failures
- no encryption-at-rest beyond host defaults
- no structured audit log beyond stdout and SQLite metadata
