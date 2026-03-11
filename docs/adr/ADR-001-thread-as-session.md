# ADR-001: Use Gmail Thread ID as Session Key

- Status: Accepted
- Date: 2026-03-11
- Last verified against commit `7317103`

## Context
The product requirement is email-native conversations with continuity per thread.

## Decision
Use Gmail `threadId` as the canonical session key and store latest OpenAI `response.id` in `thread_state`.

## Consequences
### Positive
- natural alignment with user email behavior
- no separate session identifiers required

### Negative
- context continuity depends on user staying in same Gmail thread
- no cross-thread memory stitching

## Evidence in code
- `app/gmail_worker.py` (`thread_id = full.get("threadId")`)
- `app/state.py` (`thread_state` table)
- `app/ai_agent.py` (`previous_response_id`)
