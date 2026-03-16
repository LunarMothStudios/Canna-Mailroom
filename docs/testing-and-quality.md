# Testing And Quality

## Current Automated Checks

The repo now includes:

- syntax and import validation with `compileall`
- unit tests for:
  - `DispensaryCxToolset` dispatch
  - provider loading, including custom order-provider factories
  - `ManualKnowledgeProvider`
  - `ManualOrderProvider`
  - `DutchieOrderProvider`
  - `EmailAgent` tool-loop behavior
  - `EmailThreadWorker` happy path, skips, retries, and dead-lettering
  - `SYSTEM_PROMPT.md` CX guardrails

GitHub Actions runs:

```bash
python -m compileall app scripts
python -m unittest discover -s tests
```

## Local Verification

Run:

```bash
source .venv/bin/activate
python3.11 -m compileall app tests scripts
python3.11 -m unittest discover -s tests
```

## Manual Mailbox Checks

Verify all of the following against a real mailbox:

- an order-status email with a known order number gets a grounded reply
- an hours or payment question uses store-owned knowledge
- an ambiguous multi-location question asks which store the customer means
- a cancellation or refund request does not promise action
- a second reply in the same thread preserves continuity
- dead-letter inspection and requeue work as expected

## Remaining Gaps

- no mocked tests for Gmail or `gog` transports
- no integration test for startup wiring across all provider combinations
- no end-to-end mailbox tests in CI
- no load or performance testing
