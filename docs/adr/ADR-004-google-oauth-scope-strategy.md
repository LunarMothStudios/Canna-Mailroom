# ADR-004: Use Broad Google OAuth Scopes For The MVP

- Status: Accepted
- Date: 2026-03-11
- Last verified against commit `b6c46e6`

## Context

The agent must read and send Gmail, list Drive files, and create, append, and read Google Docs. The fastest path is to request scopes broad enough to avoid permission friction during MVP validation.

## Decision

Request these scopes:

- `https://mail.google.com/`
- `https://www.googleapis.com/auth/drive`
- `https://www.googleapis.com/auth/documents`

## Consequences

Positive:
- supports the current feature set with one auth flow
- avoids repeated permission failures during setup and demos

Negative:
- larger blast radius if token material is exposed
- not least-privilege

## Follow-Up

Reduce scopes and add stronger policy controls before wider deployment.

## Evidence In Code

- `app/google_clients.py` defines the `SCOPES` constant
