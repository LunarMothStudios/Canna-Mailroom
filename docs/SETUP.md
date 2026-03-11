# Setup Guide (Local)

## 1) Prerequisites

- Python 3.11+
- OpenAI API key
- Google Cloud project
- A dedicated Gmail account for the agent

## 2) Google Cloud configuration

In your Google Cloud project:

1. Enable APIs:
   - Gmail API
   - Google Drive API
   - Google Docs API
2. Configure OAuth consent screen.
3. Create OAuth client credentials of type **Desktop app**.
4. Download JSON as `credentials.json` into repo root.

## 3) Install project

```bash
cd /Users/glitch/Projects/canna-mailroom
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

## 4) Configure `.env`

Required:

- `OPENAI_API_KEY`
- `AGENT_EMAIL` (exact Gmail address used by OAuth)

Optional:

- `OPENAI_MODEL` (default `gpt-5.4`)
- `POLL_SECONDS` (default `20`)
- `GOOGLE_DRIVE_DEFAULT_FOLDER_ID`
- `SYSTEM_PROMPT_FILE`

## 5) Run OAuth once

```bash
source .venv/bin/activate
python scripts/auth_google.py
```

This opens a browser consent flow and writes `token.json`.

## 6) Start service

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8787
```

Check health:

```bash
curl http://127.0.0.1:8787/healthz
```

Optional manual poll trigger:

```bash
curl -X POST http://127.0.0.1:8787/process-now
```

## 7) Validate end-to-end

1. Send an email from another address to `AGENT_EMAIL`.
2. Wait one poll cycle (default <= 20s).
3. Confirm reply appears in same thread.
4. Reply again in-thread.
5. Confirm response preserves context from prior turns.

---

## Common gotchas

- Wrong Gmail account during OAuth -> replies may fail or read wrong inbox.
- Missing scopes in token -> delete `token.json`, rerun auth.
- `.env` not loaded -> verify file exists at repo root and app launched from repo root.
