# CLI Reference

_Last verified against commit `b6c46e6`._

The operator surface is made up of:

- the `mailroom` CLI in `app/cli.py`
- Make targets in `Makefile`
- HTTP endpoints exposed by `app/main.py`

All runtime tuning happens through environment variables, not command flags.

## Command Surface At A Glance

| Command surface | Source | Purpose |
|---|---|---|
| `mailroom setup` | `app/cli.py` | interactive setup wizard for `.env` plus provider-specific onboarding |
| `mailroom connections` | `app/cli.py` | rerun only the mailbox connection flow for the current provider |
| `mailroom doctor` | `app/cli.py` | local health check for config, provider prerequisites, and Python deps |
| `mailroom auth` | `app/cli.py` | run the Google OAuth browser flow for `google_api` mode |
| `mailroom run` | `app/cli.py` | start the FastAPI app directly |
| `make setup` | `Makefile` | create `.venv` and install the package editable |
| `make wizard` | `Makefile` | run `mailroom setup` inside `.venv` |
| `make connections` | `Makefile` | run `mailroom connections` inside `.venv` |
| `make auth` | `Makefile` | run `mailroom auth` inside `.venv` |
| `make doctor` | `Makefile` | run `mailroom doctor` inside `.venv` |
| `make run` | `Makefile` | run `mailroom run --reload` inside `.venv` |
| HTTP endpoints | `app/main.py` | health checks, hook ingress, dead-letter inspection, and replay |

## Make Targets

### `make setup`

Creates `.venv` with Python 3.11, upgrades packaging tools, and installs the package editable.

```bash
make setup
```

Equivalent:

```bash
python3.11 -m venv .venv
. .venv/bin/activate && python -m pip install --upgrade pip setuptools wheel
. .venv/bin/activate && pip install -e .
```

If your Python 3.11 binary is not named `python3.11`, override it:

```bash
make setup PYTHON=/path/to/python3.11
```

### `make wizard`

Runs the full interactive setup wizard.

```bash
make wizard
```

### `make connections`

Reruns only the mailbox connection flow.

```bash
make connections
```

### `make auth`

Runs the Google OAuth browser flow. This is only relevant in `google_api` mode.

```bash
make auth
```

### `make doctor`

Runs local config and dependency checks.

```bash
make doctor
```

### `make run`

Starts Uvicorn on port `8787` with `--reload`.

```bash
make run
```

Notes:
- `google_api` mode starts the polling thread.
- `gog` mode starts the watcher manager instead of the polling thread.

## Mailroom CLI

### `mailroom setup`

Interactive wizard that:
- creates `.env` from `.env.example` when needed
- prompts for `OPENAI_API_KEY`, `MAIL_PROVIDER`, `AGENT_EMAIL`, model, and core runtime settings
- hands off to the provider-specific connection flow
- prints the next commands to run

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

### `mailroom connections`

Reruns just the mailbox setup flow using the current `.env`.

Use this when:
- you want to switch providers
- you want to change `gog` watcher settings
- you want to rerun only the Google connection steps without re-entering the OpenAI settings

```bash
source .venv/bin/activate
mailroom connections
```

### `mailroom doctor`

Checks:
- Python version
- `.env` and required env values
- provider-specific prerequisites
- core Python dependencies
- optional helper commands such as `gcloud`, `gws`, and `sqlite3`

Provider-specific checks:

| Provider | Blocking checks |
|---|---|
| `google_api` | `credentials.json`, `token.json`, OAuth client structure |
| `gog` | `GOG_GMAIL_TOPIC`, `GOG_GMAIL_SUBSCRIPTION`, `GOG_GMAIL_PUSH_ENDPOINT`, hook tokens, `gog` on `PATH` |

```bash
source .venv/bin/activate
mailroom doctor
```

### `mailroom auth`

Runs the Google OAuth browser flow using the current `.env` paths.

Notes:
- only used for `MAIL_PROVIDER=google_api`
- returns immediately in `gog` mode

```bash
source .venv/bin/activate
mailroom auth
```

### `mailroom run`

Starts the FastAPI app directly.

```bash
source .venv/bin/activate
mailroom run --reload
```

## Direct App Invocation

If you do not want to use `mailroom run`, the direct command is:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8787
```

## HTTP Operator Endpoints

### `GET /healthz`

```bash
curl http://127.0.0.1:8787/healthz
```

Response fields:
- `ok`
- `agent_email`
- `mail_provider`
- `ingress_mode`
- `poll_seconds`
- `worker_alive`
- `watcher_alive`
- `retry`

Interpretation:
- `ingress_mode=poll` means `google_api`
- `ingress_mode=hook` means `gog`
- `watcher_alive` is meaningful only in `gog` mode

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
        "id": "demo-1",
        "threadId": "demo-thread",
        "from": "human@example.com",
        "subject": "Hello",
        "body": "Test message"
      }
    ]
  }'
```

Notes:
- enabled only in `gog` mode
- accepts either `Authorization: Bearer ...` or `X-Mailroom-Token`
- queues background processing and returns `202`

### `GET /dead-letter`

```bash
curl http://127.0.0.1:8787/dead-letter
```

Returns recent dead-letter rows from SQLite.

### `POST /dead-letter/requeue/{message_id}`

Marks a dead-letter item as `requeued`, removes its processed-message dedupe row, and optionally reprocesses it immediately.

```bash
curl -X POST "http://127.0.0.1:8787/dead-letter/requeue/<message_id>?process_now=true"
```

Notes:
- immediate processing is most useful in `google_api` mode
- in `gog` mode, replay still depends on a cached `inbound_messages` snapshot because the provider does not refetch by ID

## Practical Recipes

### Simplest Local Email Test

```bash
make setup
source .venv/bin/activate
mailroom setup
mailroom doctor
mailroom run --reload
```

Choose `MAIL_PROVIDER=google_api` during setup, then:

```bash
curl http://127.0.0.1:8787/healthz
```

Send an email from a different mailbox to `AGENT_EMAIL`.

### Switch To `gog` Mode

```bash
source .venv/bin/activate
mailroom connections
mailroom doctor
mailroom run --reload
```

Use this only after you have:
- `gog` installed and authenticated
- one deployer-owned GCP project and Pub/Sub topic
- a public HTTPS push endpoint that forwards to the local watcher

### Replay A Failed Message

```bash
curl http://127.0.0.1:8787/dead-letter
curl -X POST "http://127.0.0.1:8787/dead-letter/requeue/<message_id>?process_now=true"
```

## Troubleshooting By Command

| Command | Symptom | Likely cause | Response |
|---|---|---|---|
| `mailroom setup` | email prompt keeps rejecting input | invalid address entered | enter a real email address such as `agent@example.com` |
| `mailroom setup` | stops at credentials step | `google_api` mode with missing OAuth client | finish the wizard’s `credentials.json` flow |
| `mailroom connections` | asks for GCP topic info | `gog` mode selected | this mode needs one deployer-owned GCP project for Gmail Pub/Sub |
| `mailroom doctor` | reports missing `GOG_GMAIL_PUSH_ENDPOINT` | `gog` ingress is not routable yet | configure a public HTTPS push path |
| `mailroom auth` | exits immediately | current provider is `gog` | this is expected; `mailroom auth` is only for `google_api` |
| `make run` | app crashes at startup | missing env var, bad token, missing `gog`, or invalid watcher config | inspect console output and rerun `mailroom doctor` |
| `POST /process-now` | returns unsupported error | app is in `gog` mode | use real Gmail hook delivery or test `/hooks/gmail` directly |
