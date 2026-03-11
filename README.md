# Canna Mailroom 🌿📬

Email-native AI agent that runs on your local machine/server and treats Gmail threads as persistent sessions.

## What it does (v0.1)

- Watches an inbox for unread messages
- Replies in-thread from the agent's Gmail account
- Persists per-thread AI context via `previous_response_id`
- Supports Google Drive + Google Docs tool use from inside agent responses:
  - list files
  - create docs
  - append docs
  - read docs

## Architecture

- **FastAPI** service
- **Gmail API** for read/send/thread handling
- **Google Drive + Docs API** for workspace actions
- **OpenAI Responses API** for agent reasoning + tool calling
- **SQLite** for thread session state and dedupe

## Prereqs

- Python 3.11+
- OpenAI API key
- Google Cloud project + OAuth client (Desktop app)

## 1) Google Cloud setup

1. Create a Google Cloud project.
2. Enable APIs:
   - Gmail API
   - Google Drive API
   - Google Docs API
3. Configure OAuth consent screen.
4. Create OAuth Client ID (**Desktop app**).
5. Download JSON and save as `credentials.json` in repo root.

## 2) Install

```bash
cd /Users/glitch/Projects/canna-mailroom
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Fill `.env`:

- `OPENAI_API_KEY`
- `AGENT_EMAIL` (gmail address of the agent mailbox)
- optional `GOOGLE_DRIVE_DEFAULT_FOLDER_ID`

## 3) Authorize Google account

```bash
source .venv/bin/activate
python scripts/auth_google.py
```

A browser window opens for consent. On success, `token.json` is created.

## 4) Run local server + worker

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8787
```

Health check:

```bash
curl http://127.0.0.1:8787/healthz
```

Manual processing trigger:

```bash
curl -X POST http://127.0.0.1:8787/process-now
```

## 5) Test email conversation

- Send an email to the agent Gmail account from another email.
- Agent detects unread message, replies in the same thread.
- Continue replying in-thread; context stays tied to that Gmail thread.

## Notes

- This MVP processes unread messages (`is:unread -from:me`).
- It strips quoted prior chains before sending user content to model.
- It marks inbound as read once processed.
- It uses Gmail `threadId` as session key and OpenAI `previous_response_id` for thread memory continuity.

## Documentation

- `docs/SETUP.md` — detailed local setup and auth flow
- `docs/ARCHITECTURE.md` — full component and data-flow map
- `docs/OPERATIONS.md` — runtime behavior, recovery, and scaling notes
- `docs/SECURITY.md` — current scope posture + hardening plan
- `docs/TROUBLESHOOTING.md` — common failures and fixes

## Next hardening steps

- Add allowlists (who can talk to agent)
- Add approval mode before sending external email
- Add label-based routing (different personas per label)
- Add webhooks (`users.watch`) instead of polling
- Add robust HTML parsing + signature stripping
- Add outbound rate limits and retry queue
