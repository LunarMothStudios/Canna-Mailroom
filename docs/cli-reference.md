# CLI Reference

_Last verified against commit `7317103`._

There is no custom project CLI yet. Operations are performed through Make targets, Python scripts, `uvicorn`, and HTTP endpoints.

## Make targets

Defined in `Makefile`.

### `make setup`
Creates virtual environment and installs package editable.

```bash
make setup
```

Equivalent:
```bash
python3 -m venv .venv
. .venv/bin/activate && pip install -e .
```

### `make auth`
Runs Google OAuth bootstrap script.

```bash
make auth
```

Equivalent:
```bash
. .venv/bin/activate && python scripts/auth_google.py
```

### `make run`
Starts FastAPI app (which also starts worker thread).

```bash
make run
```

Equivalent:
```bash
. .venv/bin/activate && uvicorn app.main:app --reload --port 8787
```

## Python script

### `python scripts/auth_google.py`
Purpose:
- validates OAuth flow
- writes/refreshes `token.json`
- prints granted scopes

Common use:
```bash
source .venv/bin/activate
python scripts/auth_google.py
```

## API endpoints used as operator commands

### `GET /healthz`

```bash
curl http://127.0.0.1:8787/healthz
```

Response fields:
- `ok`
- `agent_email`
- `poll_seconds`
- `worker_alive`

### `POST /process-now`

```bash
curl -X POST http://127.0.0.1:8787/process-now
```

Forces one immediate poll cycle; useful for debugging.

## Practical operator recipes

### Recipe: first-time bring-up

```bash
cp .env.example .env
# edit OPENAI_API_KEY + AGENT_EMAIL
make setup
make auth
make run
curl http://127.0.0.1:8787/healthz
```

### Recipe: re-auth Google after scope/token issue

```bash
rm -f token.json
make auth
```

### Recipe: verify worker is alive

```bash
curl http://127.0.0.1:8787/healthz | jq
```

Expected: `worker_alive: true`

## Command-level troubleshooting

| Command | Symptom | Likely cause | Fix |
|---|---|---|---|
| `make auth` | browser flow fails | missing `credentials.json` | place OAuth client file in repo root |
| `make run` | crash at startup | invalid/missing env values | verify `.env` and required keys |
| `/healthz` | `worker_alive=false` | startup failed before worker init | check console stacktrace |
| `/process-now` | `worker not initialized` | startup path incomplete | fix auth/env and restart |
