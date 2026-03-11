# ADR-004: Use Broad Google OAuth Scopes for MVP

- Status: Accepted (MVP)
- Date: 2026-03-11
- Last verified against commit `7317103`

## Context
Agent must read/send Gmail and operate on Drive/Docs quickly for validation.

## Decision
Request broad scopes:
- `https://mail.google.com/`
- `https://www.googleapis.com/auth/drive`
- `https://www.googleapis.com/auth/documents`

## Consequences
### Positive
- feature-complete behavior without scope-friction

### Negative
- larger blast radius if account/token compromised
- not least-privilege

## Follow-up
Reduce scopes and add policy controls before wider deployment.

## Evidence in code
- `app/google_clients.py` (`SCOPES` constant)
