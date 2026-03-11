# ADR-005: Keep Gmail I/O in Worker, Expose Only Drive/Docs as Model Tools

- Status: Accepted
- Date: 2026-03-11
- Last verified against commit `7317103`

## Context
Need deterministic mailbox behavior while still allowing workspace actions from model decisions.

## Decision
- Gmail read/send stays in application worker code.
- Model gets only explicit function tools for Drive/Docs.
- Function-call loop capped at 6 rounds.

## Consequences
### Positive
- tighter control over email side effects
- clear separation between transport and content generation

### Negative
- model cannot autonomously browse/manage inbox beyond current message pipeline

## Evidence in code
- `app/gmail_worker.py` (all Gmail operations)
- `app/ai_agent.py` (`_tool_specs` and `_run_tool`, loop `for _ in range(6)`) 
