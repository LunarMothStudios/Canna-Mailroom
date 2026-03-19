# ADR-005: Keep Gmail I/O In The Worker And Expose Only Explicit Tools

- Status: Accepted
- Date: 2026-03-11

## Context

The product needs reliable mailbox behavior, but still wants the model to use a very small set of explicit dispensary CX tools.

## Decision

- keep Gmail read and send logic entirely in `GmailThreadWorker`
- expose only explicit function tools from `EmailAgent._tool_specs()`
- cap the tool loop at six rounds

Current tool surface:

- `lookup_order`
- `search_store_knowledge`

## Consequences

Positive:
- recipient, thread, and send timing remain application-controlled
- tool exposure is explicit and auditable
- the model cannot directly inspect or modify the inbox

Negative:
- the model cannot autonomously manage mailbox state beyond the current inbound message
- adding new capabilities requires code changes rather than prompt changes alone

## Evidence In Code

- `app/gmail_worker.py` owns Gmail operations
- `app/ai_agent.py` defines the six-round tool loop
- `app/cx_toolset.py` defines the explicit two-tool surface
