# Database Guidelines

> Django ORM contracts for backend data access in this project.

---

## Overview

The Django backend uses app-local models plus service-layer transactions. For AI task lifecycle work, the durable state is `apps.ai.models.AITask`; billing reservation/settlement state is linked through `billing.WalletReservation` and `billing.CodexUsageEvent`.

Do not move task lifecycle decisions into views, management commands, or frontend state. Persist enough state on `AITask` for reload, retry, worker recovery, and billing reconciliation.

---

## AI Task Model Contract

`AITask` is the refresh-safe public task record.

Required fields and meaning:

- `task_id`: public stable ID returned to clients as `task.id`; unique; generated as `aitask_<24-char-sha1>` when possible.
- `idempotency_key`: unique duplicate-submit key. Reuse by the same user returns the existing task; reuse by another user is rejected.
- `call_id`: billing/provider correlation ID; indexed; billable tasks generate `ai_<24-char-sha1>` when omitted.
- `task_type`: product worker discriminator such as `writing_score`.
- `status`: one of `pending`, `running`, `succeeded`, `failed`, `fallback`, `cancelled`.
- `attempt_count`, `max_attempts`, `available_at`, `started_at`, `finished_at`, `worker_id`: worker lease, retry, and recovery state.
- `request_payload`, `result_payload`, `metadata`: JSON state needed to complete or inspect a task after browser refresh.
- `billing_reservation`, `usage`: optional links to wallet reservation and settled usage.

Terminal statuses are `succeeded`, `failed`, `fallback`, and `cancelled`. Terminal rows must not be mutated by late worker callbacks except for safe no-op reloads.

---

## Transaction Patterns

Use `transaction.atomic()` plus `select_for_update()` for state transitions that touch task status or wallet state.

Required patterns:

- `create_ai_task(...)` locks by `idempotency_key` before create and returns `(task, created)`.
- `claim_ai_task(task_id, worker_id)` locks by `task_id`, only claims `pending`, increments `attempt_count`, sets `running`, and records `started_at`.
- `recover_running_ai_task(...)` locks the task, requeues stale `running` tasks if attempts remain, or marks `failed` when exhausted.
- `create_billable_ai_task(...)` reserves wallet balance before creating the task and links the `WalletReservation`.
- Billing-aware terminal helpers release/settle reservations through `apps.ai.orchestration`, not directly from views or commands.

Do not update `AITask.status`, wallet balances, reservation status, or usage links with ad hoc `.update()` calls in product flows. Tests may use direct updates only to simulate stale rows.

---

## Billing Reservation Contract

Billable AI tasks must keep reservation and task identity coupled:

- `reserved_u` is an integer in micro RMB and must be greater than zero.
- Billable task creation requires `idempotency_key`.
- The first create reserves wallet balance with `reserve_usage(user, call_id, reserved_u)`.
- Duplicate create with the same key and same user returns the existing task and must not create another reservation.
- Duplicate key or call ID owned by another user is rejected.
- Successful completion calls `settle_usage(...)` and links `AITask.usage` when a usage event exists.
- `fallback`, terminal `failed`, and `cancelled` release the reservation when it is still `reserved`.
- Retryable non-terminal failures keep the reservation.

`settle_usage(...)` may return `pending_reconciliation` when authoritative usage is missing. The AI task can still succeed, but later reconciliation must use the same `call_id` idempotency.

---

## Migrations

AI task lifecycle schema changes require migrations under `backend_django/apps/ai/migrations/` and must keep old rows compatible:

- New task states require updating `AITask.Status` and adding a migration when choices are materialized.
- Nullable/backfilled fields are preferred for existing production rows.
- After model changes, run `manage.py makemigrations --check --dry-run` and the targeted app tests.

---

## Query Patterns

Worker queries must be deterministic and bounded:

- Pending work: filter `status=pending`, `available_at is null or <= now`, order by `created_at`, then apply `--limit`.
- Stale work: filter `status=running`, `started_at <= now - stale_after_seconds`, order by `started_at`, `created_at`.
- User-facing lookup: always filter by `user` and `task_id`; never expose a task by public ID without ownership.

---

## Common Mistakes

- Creating a billable task without an `idempotency_key`; this risks duplicate wallet reservations.
- Settling or releasing wallet reservations outside `apps.ai.orchestration`; this decouples wallet and task terminal state.
- Treating `fallback` as success; it is terminal and releases billing, but it means default output was used.
- Failing stale `running` tasks immediately; recovery should requeue while `attempt_count < max_attempts`.
