# Documentation Index

_Last verified against commit `b09c4f1`._

## Start Here By Audience

| Audience | Read first | Why |
|---|---|---|
| Developer | [architecture.md](architecture.md), [runtime-and-pipeline.md](runtime-and-pipeline.md), [data-model.md](data-model.md) | Understand how the service starts, processes mail, stores state, and calls tools |
| Operator | [README.md](../README.md), [cli-reference.md](cli-reference.md), [operations.md](operations.md), [security-and-safety.md](security-and-safety.md) | Bring up the system, monitor it, and recover from failures safely |
| Stakeholder | [README.md](../README.md), [architecture.md](architecture.md), [faq.md](faq.md) | Understand value, current scope, and operational boundaries without reading code |

## Recommended Reading Order

1. [architecture.md](architecture.md)
2. [runtime-and-pipeline.md](runtime-and-pipeline.md)
3. [data-model.md](data-model.md)
4. [operations.md](operations.md)
5. [security-and-safety.md](security-and-safety.md)

## Full Documentation Set

- [architecture.md](architecture.md) — system shape, ownership boundaries, startup, and tool exposure
- [data-model.md](data-model.md) — SQLite tables, conceptual relationships, and persistence checkpoints
- [runtime-and-pipeline.md](runtime-and-pipeline.md) — stage-by-stage mail processing, retries, and job lifecycle
- [cli-reference.md](cli-reference.md) — Make targets, scripts, HTTP endpoints, recipes, and troubleshooting
- [operations.md](operations.md) — day-1 setup, day-2 runbook, incidents, and recovery
- [deployment.md](deployment.md) — local and single-host deployment guidance plus cloud fit notes
- [security-and-safety.md](security-and-safety.md) — secrets, scopes, data handling, approval model, and safe defaults
- [testing-and-quality.md](testing-and-quality.md) — current quality bar, manual checks, CI behavior, and release checklist
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
| `app/settings.py` | [README.md](../README.md), [cli-reference.md](cli-reference.md), [operations.md](operations.md) |
| `app/google_clients.py` | [architecture.md](architecture.md), [security-and-safety.md](security-and-safety.md), [deployment.md](deployment.md) |
| `app/state.py` | [data-model.md](data-model.md), [runtime-and-pipeline.md](runtime-and-pipeline.md), [operations.md](operations.md) |
| `app/ai_agent.py` | [architecture.md](architecture.md), [runtime-and-pipeline.md](runtime-and-pipeline.md), [security-and-safety.md](security-and-safety.md) |
| `app/tools.py` | [architecture.md](architecture.md), [security-and-safety.md](security-and-safety.md), [faq.md](faq.md) |
| `app/gmail_worker.py` | [architecture.md](architecture.md), [runtime-and-pipeline.md](runtime-and-pipeline.md), [operations.md](operations.md) |
| `scripts/auth_google.py` | [cli-reference.md](cli-reference.md), [operations.md](operations.md), [deployment.md](deployment.md) |
