# Documentation Index

_Last verified against commit `b6c46e6`._

## Start Here By Audience

| Audience | Read first | Why |
|---|---|---|
| Developer | [architecture.md](architecture.md), [runtime-and-pipeline.md](runtime-and-pipeline.md), [data-model.md](data-model.md) | Understand provider selection, message flow, state, and tool boundaries |
| Operator | [../README.md](../README.md), [cli-reference.md](cli-reference.md), [operations.md](operations.md), [security-and-safety.md](security-and-safety.md) | Bring up one mailbox, monitor it, and recover from failures safely |
| Stakeholder | [../README.md](../README.md), [architecture.md](architecture.md), [faq.md](faq.md) | Understand value, current scope, and major constraints without reading code |

## Recommended Reading Order

1. [architecture.md](architecture.md)
2. [runtime-and-pipeline.md](runtime-and-pipeline.md)
3. [data-model.md](data-model.md)
4. [cli-reference.md](cli-reference.md)
5. [operations.md](operations.md)

## Full Documentation Set

- [architecture.md](architecture.md) — provider-aware system shape, startup, ownership boundaries, and tool exposure
- [data-model.md](data-model.md) — SQLite tables, conceptual relationships, and persistence checkpoints
- [runtime-and-pipeline.md](runtime-and-pipeline.md) — polling and hook ingress flow, retries, and job lifecycle
- [cli-reference.md](cli-reference.md) — `mailroom`, Make targets, HTTP endpoints, recipes, and troubleshooting
- [operations.md](operations.md) — day-1 setup, day-2 runbook, incidents, and recovery
- [deployment.md](deployment.md) — local and single-host deployment guidance plus provider fit notes
- [security-and-safety.md](security-and-safety.md) — secrets, auth material, data handling, and safety gaps
- [testing-and-quality.md](testing-and-quality.md) — current quality bar, smoke checks, CI behavior, and release checklist
- [faq.md](faq.md) — short answers for operators, developers, and stakeholders

## Architecture Decision Records

- [adr/ADR-001-thread-as-session.md](adr/ADR-001-thread-as-session.md)
- [adr/ADR-002-polling-worker-model.md](adr/ADR-002-polling-worker-model.md)
- [adr/ADR-003-sqlite-state-store.md](adr/ADR-003-sqlite-state-store.md)
- [adr/ADR-004-google-oauth-scope-strategy.md](adr/ADR-004-google-oauth-scope-strategy.md)
- [adr/ADR-005-tool-loop-and-boundaries.md](adr/ADR-005-tool-loop-and-boundaries.md)
- [adr/ADR-006-outbound-reply-idempotency.md](adr/ADR-006-outbound-reply-idempotency.md)

## Module Coverage Map

| Code path | Primary docs |
|---|---|
| `app/main.py` | [architecture.md](architecture.md), [cli-reference.md](cli-reference.md), [operations.md](operations.md) |
| `app/cli.py` | [../README.md](../README.md), [cli-reference.md](cli-reference.md), [operations.md](operations.md) |
| `app/settings.py` | [../README.md](../README.md), [cli-reference.md](cli-reference.md), [operations.md](operations.md) |
| `app/mailbox.py` | [architecture.md](architecture.md), [runtime-and-pipeline.md](runtime-and-pipeline.md), [data-model.md](data-model.md) |
| `app/google_mailbox.py` | [architecture.md](architecture.md), [runtime-and-pipeline.md](runtime-and-pipeline.md), [security-and-safety.md](security-and-safety.md) |
| `app/gog_mailbox.py` | [architecture.md](architecture.md), [runtime-and-pipeline.md](runtime-and-pipeline.md), [operations.md](operations.md) |
| `app/gog_watcher.py` | [architecture.md](architecture.md), [operations.md](operations.md), [deployment.md](deployment.md) |
| `app/google_clients.py` | [architecture.md](architecture.md), [security-and-safety.md](security-and-safety.md), [deployment.md](deployment.md) |
| `app/state.py` | [data-model.md](data-model.md), [runtime-and-pipeline.md](runtime-and-pipeline.md), [operations.md](operations.md) |
| `app/ai_agent.py` | [architecture.md](architecture.md), [runtime-and-pipeline.md](runtime-and-pipeline.md), [security-and-safety.md](security-and-safety.md) |
| `app/tools.py` | [architecture.md](architecture.md), [security-and-safety.md](security-and-safety.md), [faq.md](faq.md) |
| `app/gmail_worker.py` | [architecture.md](architecture.md), [runtime-and-pipeline.md](runtime-and-pipeline.md), [operations.md](operations.md) |
| `scripts/auth_google.py` | [cli-reference.md](cli-reference.md), [operations.md](operations.md), [deployment.md](deployment.md) |
