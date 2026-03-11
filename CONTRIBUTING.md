# Contributing to Canna Mailroom

Thanks for helping improve Canna Mailroom 🌿📬

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

You will need:
- `OPENAI_API_KEY`
- Google OAuth desktop credentials (`credentials.json`)

## Run locally

```bash
make auth
make run
```

## Quality checks before PR

```bash
source .venv/bin/activate
python -m compileall app scripts
curl http://127.0.0.1:8787/healthz
```

If you change runtime behavior, update docs in `docs/` in the same PR.

## Pull request guidelines

- Keep changes focused and small.
- Explain what changed and why.
- Include manual test steps and outcomes.
- Call out any security implications (email send behavior, scopes, secrets).

## Scope expectations

High-priority contribution areas:
- reliability (retries, better error handling)
- safety controls (allowlists, approval gating)
- testing (unit/integration)
- deployment hardening

## Security

Please do **not** open public issues for sensitive vulnerabilities.
Report privately per `SECURITY.md`.
