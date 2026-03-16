# ADR-004: Use Broad Google OAuth Scopes For The MVP

- Status: Superseded
- Date: 2026-03-11

## Context

This ADR captured the earlier Google Workspace tool phase of the project, when the runtime exposed Drive and Docs actions directly to the model. The current provider-agnostic CX runtime no longer does that.

## Decision

The historical MVP requested these scopes:

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

This follow-up has now been implemented for the active runtime. `app/google_clients.py` uses only `https://mail.google.com/`.

## Evidence In Code

- `app/google_clients.py` defines the `SCOPES` constant
