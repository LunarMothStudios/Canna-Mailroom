# ADR-003: Use SQLite For Local Runtime State

- Status: Accepted
- Date: 2026-03-11
- Last verified against commit `b09c4f1`

## Context

The runtime needs small but durable state for thread continuity, dedupe, dead-letter handling, and outbound send tracking. The target environment is still a local or single-host MVP.

## Decision

Use a local SQLite database file and create the schema lazily at startup from application code.

## Consequences

Positive:
- zero additional infrastructure
- easy to back up or inspect with standard tools
- enough durability for one mailbox and one worker

Negative:
- not suitable for coordinated multi-instance processing
- no formal migration framework exists yet
- file loss resets memory, dedupe, and replay state

## Evidence In Code

- `app/settings.py` defines `STATE_DB`
- `app/state.py` creates and accesses the schema
