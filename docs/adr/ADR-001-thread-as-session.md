# ADR-001: Use Gmail Thread ID As Session Key

- Status: Accepted
- Date: 2026-03-11
- Last verified against commit `b6c46e6`

## Context

The product needs email-native continuity without inventing a second session system. Gmail already groups related conversation turns under `threadId`.

## Decision

Use Gmail `threadId` as the canonical conversation key and persist the latest OpenAI `response.id` for that thread in `thread_state`.

## Consequences

Positive:
- aligns directly with how users already experience an email thread
- keeps the state model very small
- makes replay and inspection easier because thread identity comes from Gmail itself

Negative:
- continuity is lost when a human starts a new Gmail thread
- there is no memory stitching across separate threads

## Evidence In Code

- `app/gmail_worker.py` reads `threadId` from Gmail messages
- `app/state.py` persists `thread_state`
- `app/ai_agent.py` sends `previous_response_id`
