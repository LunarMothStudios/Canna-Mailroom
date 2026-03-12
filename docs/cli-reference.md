# CLI Reference

_Last verified against commit `b09c4f1`._

There is no custom project CLI. The operational surface is made up of:

- Make targets in `Makefile`
- one bootstrap script in `scripts/auth_google.py`
- direct `uvicorn` invocation
- HTTP endpoints exposed by `app/main.py`

All runtime tuning happens through environment variables, not command flags.

## Command Surface At A Glance

| Command surface | Source | Purpose |
|---|---|---|
| `make setup` | `Makefile` | create `.venv` and install the package editable |
| `make auth` | `Makefile` | run Google OAuth bootstrap |
| `make run` | `Makefile` | start FastAPI and the background worker |
| `python scripts/auth_google.py` | `scripts/auth_google.py` | create or refresh `token.json` |
| `uvicorn app.main:app --reload --port 8787` | direct invocation used by `make run` | start the app without Make |
| HTTP endpoints | `app/main.py` | health checks, manual polling, dead-letter inspection, replay |

## Make Targets

### `make setup`

Creates `.venv` and installs the package in editable mode.

```bash
make setup
```

Equivalent:

```bash
python3 -m venv .venv
. .venv/bin/activate && pip install -e .
```

### `make auth`

Runs the Google OAuth bootstrap script.

```bash
make auth
```

Equivalent:

```bash
. .venv/bin/activate && python scripts/auth_google.py
```

### `make run`

Starts Uvicorn on port `8787` with `--reload`. The FastAPI startup hook then builds the worker and starts the polling thread.

```bash
make run
```

Equivalent:

```bash
. .venv/bin/activate && uvicorn app.main:app --reload --port 8787
```

Notes:
- `--reload` is convenient for local development.
- There are no app-specific CLI flags for model, poll interval, or retry tuning. Use `.env` and restart.

## Python Script

### `python scripts/auth_google.py`

Behavior:
- loads settings from `.env`
- invokes `get_credentials(...)`
- launches the Google OAuth desktop flow when needed
- writes or refreshes `token.json`
- prints the saved token path and granted scopes

Example:

```bash
source .venv/bin/activate
python scripts/auth_google.py
```

There are no script flags.

## Direct App Invocation

If you do not want to use `make run`, the direct command is:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8787
```

For a less development-oriented single-host run, remove `--reload`:

```bash
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8787
```

## HTTP Operator Endpoints

### `GET /healthz`

Checks whether the app is alive and whether the worker thread is still running.

```bash
curl http://127.0.0.1:8787/healthz
```

Response fields:
- `ok`
- `agent_email`
- `poll_seconds`
- `worker_alive`
- `retry.max_attempts`
- `retry.base_delay_ms`
- `retry.max_delay_ms`
- `retry.jitter_ms`

### `POST /process-now`

Runs one immediate processing cycle in the current process.

```bash
curl -X POST http://127.0.0.1:8787/process-now
```

Response fields:
- `ok`
- `processed`

`processed` counts only successful message runs. Messages skipped as self-messages or empty bodies do not increment the count.

### `GET /dead-letter`

Returns recently dead-lettered messages from SQLite.

Default:

```bash
curl http://127.0.0.1:8787/dead-letter
```

With explicit limit:

```bash
curl "http://127.0.0.1:8787/dead-letter?limit=100"
```

Notes:
- `limit` defaults to `50`
- the endpoint clamps `limit` into the range `1..200`

Response fields per item:
- `message_id`
- `thread_id`
- `from_email`
- `subject`
- `error`
- `attempts`
- `status`
- `updated_at`

### `POST /dead-letter/requeue/{message_id}`

Marks a dead-letter item as `requeued`, removes its processed-message dedupe row, and optionally reprocesses it immediately.

Requeue and process now:

```bash
curl -X POST "http://127.0.0.1:8787/dead-letter/requeue/<message_id>?process_now=true"
```

Requeue without immediate processing:

```bash
curl -X POST "http://127.0.0.1:8787/dead-letter/requeue/<message_id>?process_now=false"
```

Response fields:
- `ok`
- `requeued`
- `processed_now`

## Practical Recipes

### First-Time Bring-Up

```bash
cp .env.example .env
# edit OPENAI_API_KEY and AGENT_EMAIL
make setup
make auth
make run
curl http://127.0.0.1:8787/healthz
```

### Force One Poll Cycle During Debugging

```bash
curl -X POST http://127.0.0.1:8787/process-now
```

### Inspect Dead Letters

```bash
curl "http://127.0.0.1:8787/dead-letter?limit=20"
```

### Requeue A Failed Message For The Next Normal Cycle

```bash
curl -X POST "http://127.0.0.1:8787/dead-letter/requeue/<message_id>?process_now=false"
```

### Requeue And Replay Immediately

```bash
curl -X POST "http://127.0.0.1:8787/dead-letter/requeue/<message_id>?process_now=true"
```

### Re-Run Google OAuth

```bash
rm -f token.json
make auth
```

## Troubleshooting By Command

| Command | Symptom | Likely cause | What to check |
|---|---|---|---|
| `make setup` | install fails | Python version or network issue | verify Python 3.11+ and package install output |
| `make auth` | OAuth flow does not start | missing `credentials.json` | confirm `GOOGLE_CREDENTIALS_FILE` path and file presence |
| `make auth` | token refresh fails | revoked or incompatible token | remove `token.json` and rerun auth |
| `make run` | app crashes at startup | missing env var, bad token, missing prompt file | inspect console output and validate `.env` paths |
| `GET /healthz` | `worker_alive=false` | worker thread never started or died | restart and inspect startup logs |
| `POST /process-now` | `worker not initialized` | startup did not finish successfully | fix startup problem and restart |
| `GET /dead-letter` | empty list when failures are expected | failure happened before dead-letter path or wrong `STATE_DB` file | verify active state DB path |
| `POST /dead-letter/requeue/...` | `processed_now=false` | replay still failing or message already processed again | inspect `/dead-letter` and console logs |
