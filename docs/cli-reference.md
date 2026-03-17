# CLI Reference

The operator surface is made up of:

- the `mailroom` CLI in `app/cli.py`
- Make targets in `Makefile`
- HTTP endpoints exposed by `app/main.py`

All runtime tuning happens through environment variables, not command flags.

## Command Surface

| Command | Purpose |
|---|---|
| `mailroom setup` | interactive setup wizard for `.env`, CX providers, and mailbox connection |
| `mailroom connections` | rerun only the mailbox connection flow |
| `mailroom access` | rerun only the sender access policy flow |
| `mailroom doctor` | local health check for config, provider prerequisites, and Python deps |
| `mailroom auth` | run the Google OAuth browser flow for `google_api` mode |
| `mailroom run` | start the FastAPI app directly |
| `make setup` | create `.venv` and install the package editable |
| `make wizard` | run `mailroom setup` inside `.venv` |
| `make connections` | run `mailroom connections` inside `.venv` |
| `make access` | run `mailroom access` inside `.venv` |
| `make auth` | run `mailroom auth` inside `.venv` |
| `make doctor` | run `mailroom doctor` inside `.venv` |
| `make run` | run `mailroom run --reload` inside `.venv` |

## Make Targets

### `make setup`

```bash
make setup
```

Equivalent:

```bash
python3.11 -m venv .venv
. .venv/bin/activate && python -m pip install --upgrade pip setuptools wheel
. .venv/bin/activate && pip install -e .
```

### `make wizard`

```bash
make wizard
```

Runs the full interactive setup wizard.

### `make connections`

```bash
make connections
```

Reruns only the mailbox connection flow.

### `make access`

```bash
make access
```

Reruns only the sender access policy flow.

### `make auth`

```bash
make auth
```

Runs the Google OAuth browser flow. Only relevant in `google_api` mode.

### `make doctor`

```bash
make doctor
```

Runs local config and dependency checks.

### `make run`

```bash
make run
```

Starts Uvicorn on port `8787` with `--reload`.

## `mailroom setup`

Interactive wizard that:

- creates `.env` from `.env.example` when needed
- prompts for base runtime settings
- configures the dispensary CX providers
- hands off to the mailbox-specific connection flow
- prints the next commands to run

It currently prompts for:

- `OPENAI_API_KEY`
- `MAIL_PROVIDER`
- `AGENT_EMAIL`
- `SENDER_POLICY_MODE`
- `ALLOWED_SENDERS` when needed
- `OPENAI_MODEL`
- `POLL_SECONDS`
- `KNOWLEDGE_PROVIDER`
- `STORE_KNOWLEDGE_FILE`
- `ORDER_PROVIDER`
- either `MANUAL_ORDER_FILE`, Dutchie credentials, Treez credentials, bridge settings, or `ORDER_PROVIDER_FACTORY`

Provider behavior:

| Provider | What setup covers |
|---|---|
| `google_api` | local `credentials.json`, `token.json`, and browser auth |
| `gog` | `gog` account, Pub/Sub topic, hook tokens, serve settings, and optional `gcloud` / `gog` helper commands |

Example:

```bash
source .venv/bin/activate
mailroom setup
```

## `mailroom connections`

Reruns just the mailbox setup flow using the current `.env`.

Use this when:

- you want to switch between `google_api` and `gog`
- you want to change `gog` watcher settings
- you want to rerun only the Google mailbox auth steps

```bash
source .venv/bin/activate
mailroom connections
```

## `mailroom access`

Reruns just the sender access policy flow using the current `.env`.

Use this when:

- you want to switch between `all` and `allowlist`
- you want to update the approved sender list

```bash
source .venv/bin/activate
mailroom access
```

## `mailroom doctor`

Checks:

- Python version
- `.env` and required env values
- provider-specific prerequisites
- core Python dependencies
- optional helper commands such as `gcloud` and `sqlite3`

Blocking checks include:

| Area | Checks |
|---|---|
| mailbox mode | `MAIL_PROVIDER`, Gmail OAuth files for `google_api`, `gog` runtime vars for `gog` |
| CX config | `ORDER_PROVIDER`, `KNOWLEDGE_PROVIDER`, `STORE_KNOWLEDGE_FILE`, plus provider-specific order config |
| sender policy | `SENDER_POLICY_MODE`, `ALLOWED_SENDERS` when allowlist mode is used |
| Python deps | `openai`, `fastapi`, `uvicorn` importability |

Order-provider specific checks:

| `ORDER_PROVIDER` | Doctor checks |
|---|---|
| `manual` | `MANUAL_ORDER_FILE` exists |
| `dutchie` | `DUTCHIE_LOCATION_KEY` and `DUTCHIE_API_BASE_URL` are set |
| `treez` | `TREEZ_DISPENSARY`, `TREEZ_CLIENT_ID`, `TREEZ_API_KEY`, and `TREEZ_API_BASE_URL` are set |
| `jane` | `JANE_BRIDGE_URL` is set |
| `bridge` | `BRIDGE_ORDER_PROVIDER_URL`, `BRIDGE_ORDER_PROVIDER_SOURCE`, and `BRIDGE_ORDER_PROVIDER_TIMEOUT_SECONDS` are set |
| `custom` | `ORDER_PROVIDER_FACTORY` imports successfully |

```bash
source .venv/bin/activate
mailroom doctor
```

## `mailroom auth`

Runs the Google OAuth browser flow using the current `.env` paths.

Notes:

- only used for `MAIL_PROVIDER=google_api`
- returns immediately in `gog` mode

```bash
source .venv/bin/activate
mailroom auth
```

## `mailroom run`

Starts the FastAPI app directly.

```bash
source .venv/bin/activate
mailroom run --reload
```

## Direct App Invocation

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8787
```

## HTTP Endpoints

### `GET /healthz`

```bash
curl http://127.0.0.1:8787/healthz
```

Response fields:

- `ok`
- `agent_email`
- `mail_provider`
- `sender_policy_mode`
- `allowed_senders_count`
- `ingress_mode`
- `order_provider`
- `knowledge_provider`
- `poll_seconds`
- `worker_alive`
- `watcher_alive`
- `retry`

### `POST /process-now`

Runs one immediate processing cycle in the current process.

```bash
curl -X POST http://127.0.0.1:8787/process-now
```

Notes:

- supported only in `google_api` mode
- returns an error payload in `gog` mode

### `POST /hooks/gmail`

Accepts normalized Gmail hook payloads in `gog` mode.

```bash
curl -X POST http://127.0.0.1:8787/hooks/gmail \
  -H "Authorization: Bearer <GOG_GMAIL_HOOK_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "id": "test-1",
        "threadId": "thread-1",
        "from": "human@example.com",
        "subject": "Hello",
        "body": "Can you check order 100100?"
      }
    ]
  }'
```

### `GET /dead-letter`

Returns dead-letter rows from SQLite.

```bash
curl "http://127.0.0.1:8787/dead-letter?limit=50"
```

### `POST /dead-letter/requeue/{message_id}`

Marks a dead-letter row as `requeued`, removes its processed-message dedupe row, and optionally reprocesses it immediately.

```bash
curl -X POST "http://127.0.0.1:8787/dead-letter/requeue/<message_id>?process_now=true"
```

## Core Environment Variables

| Variable | Purpose |
|---|---|
| `MAIL_PROVIDER` | selects `google_api` or `gog` |
| `AGENT_EMAIL` | mailbox address used by the runtime |
| `SENDER_POLICY_MODE` | `all` or `allowlist` |
| `ALLOWED_SENDERS` | sender allowlist when allowlist mode is used |
| `ORDER_PROVIDER` | `manual`, `dutchie`, `treez`, `jane`, `bridge`, or `custom` |
| `ORDER_PROVIDER_FACTORY` | custom Python factory path for custom order providers |
| `KNOWLEDGE_PROVIDER` | currently `manual` only |
| `STORE_KNOWLEDGE_FILE` | path to the store knowledge JSON file |
| `MANUAL_ORDER_FILE` | path to the manual orders JSON file |
| `DUTCHIE_LOCATION_KEY` | Dutchie location key for the built-in Dutchie adapter |
| `DUTCHIE_INTEGRATOR_KEY` | optional Dutchie integrator key |
| `DUTCHIE_API_BASE_URL` | Dutchie API base URL |
| `TREEZ_DISPENSARY` | Treez dispensary slug or name for the built-in Treez adapter |
| `TREEZ_CLIENT_ID` | Treez client ID for the access-token flow |
| `TREEZ_API_KEY` | Treez API key for the access-token flow |
| `TREEZ_API_BASE_URL` | Treez API base URL |
| `JANE_BRIDGE_URL` | merchant-operated Jane bridge endpoint |
| `JANE_BRIDGE_TOKEN` | optional bearer token for the Jane bridge |
| `JANE_BRIDGE_TIMEOUT_SECONDS` | request timeout for the Jane bridge |
| `BRIDGE_ORDER_PROVIDER_URL` | generic bridge endpoint for other vendors |
| `BRIDGE_ORDER_PROVIDER_TOKEN` | optional bearer token for the generic bridge |
| `BRIDGE_ORDER_PROVIDER_SOURCE` | source label returned in bridge-backed order results |
| `BRIDGE_ORDER_PROVIDER_TIMEOUT_SECONDS` | request timeout for the generic bridge |
| `GOOGLE_CREDENTIALS_FILE` | desktop OAuth client JSON for `google_api` mode |
| `GOOGLE_TOKEN_FILE` | Gmail OAuth token file for `google_api` mode |
| `SYSTEM_PROMPT_FILE` | prompt file loaded at startup |
