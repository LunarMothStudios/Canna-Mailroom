# ADR-003: Use SQLite for Local Runtime State

- Status: Accepted
- Date: 2026-03-11
- Last verified against commit `7317103`

## Context
MVP needs minimal persistence for dedupe and thread continuity.

## Decision
Use local SQLite (`state.db`) with lazy schema init in application code.

## Consequences
### Positive
- zero infrastructure dependency
- easy local portability

### Negative
- not ideal for multi-instance concurrency
- no migration/versioning framework yet

## Evidence in code
- `app/settings.py` (`STATE_DB`)
- `app/state.py` (`CREATE TABLE IF NOT EXISTS` + read/write methods)
