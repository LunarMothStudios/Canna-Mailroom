# Canna Mailroom 🌿📬

_Last verified against commit `7317103`._

Canna Mailroom is an **email-native AI agent runtime**. It watches a Gmail inbox, treats each Gmail thread as a session, and replies in-thread using OpenAI Responses API context chaining.

It can also use tools during replies:
- research the public web (`research_web`, via OpenAI web search tool)
- read/list files in Drive
- create Google Docs
- append to existing Docs
- read Doc content

## Who this is for

- **Developers** building an email agent MVP quickly
- **Operators** running a mailbox-backed automation service
- **Stakeholders** validating whether “AI over email threads” is viable

## 5-minute quickstart

1. **Install**
   ```bash
   cd /Users/glitch/Projects/canna-mailroom
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .
   cp .env.example .env
   ```

2. **Set required env values in `.env`**
   - `OPENAI_API_KEY`
   - `AGENT_EMAIL`

3. **Add Google OAuth client file**
   - Place `credentials.json` at repo root

4. **Authorize Google account**
   ```bash
   make auth
   ```

5. **Run service**
   ```bash
   make run
   ```

6. **Sanity check**
   ```bash
   curl http://127.0.0.1:8787/healthz
   ```

7. Send an email to `AGENT_EMAIL`, then reply in the same thread to verify session continuity.

Default persona is defined in `SYSTEM_PROMPT.md` (currently: **Mellow Sloth** 🦥🌿).

## Key commands

```bash
make setup        # create venv + install
make auth         # run Google OAuth and create token.json
make run          # start API + background worker

curl http://127.0.0.1:8787/healthz
curl -X POST http://127.0.0.1:8787/process-now
curl http://127.0.0.1:8787/dead-letter
curl -X POST http://127.0.0.1:8787/dead-letter/requeue/<message_id>
```

## What is implemented (from code)

- Gmail polling query: `is:unread -from:me` (`app/gmail_worker.py`)
- Poll interval: `POLL_SECONDS` (default 20) (`app/settings.py`)
- Thread memory persistence in SQLite:
  - `thread_state(thread_id, last_response_id)`
  - `processed_messages(message_id)` (`app/state.py`)
- Response continuity via `previous_response_id` (`app/ai_agent.py`)
- Tool-call loop max depth: 6 rounds (`app/ai_agent.py`)
- Retry + backoff for transient failures with dead-letter persistence for exhausted runs (`app/gmail_worker.py`, `app/state.py`)

## Open source project hygiene

- License: [MIT](LICENSE)
- Contribution guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Security policy: [SECURITY.md](SECURITY.md)
- CI: GitHub Actions compile check (`.github/workflows/ci.yml`)

## Documentation index

- [docs/index.md](docs/index.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/data-model.md](docs/data-model.md)
- [docs/runtime-and-pipeline.md](docs/runtime-and-pipeline.md)
- [docs/cli-reference.md](docs/cli-reference.md)
- [docs/operations.md](docs/operations.md)
- [docs/deployment.md](docs/deployment.md)
- [docs/security-and-safety.md](docs/security-and-safety.md)
- [docs/testing-and-quality.md](docs/testing-and-quality.md)
- [docs/faq.md](docs/faq.md)
- [docs/adr/](docs/adr)
