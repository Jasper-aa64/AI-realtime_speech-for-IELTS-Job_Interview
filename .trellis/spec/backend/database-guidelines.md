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
- `provider` and `model`: durable worker-routing hints. For the current local worker boundary, `writing_score` with `provider=mock_success` uses the deterministic success adapter; other `writing_score` values keep the explicit fallback adapter until a real provider integration exists.

Provider routing must go through `apps.ai.provider_config`:

- `AI_DEFAULT_PROVIDER` chooses the durable default provider string stored on new tasks when the request omits `provider`.
- `AI_ALLOW_MOCK_SUCCESS` gates `provider=mock_success`. When disabled, the worker must fall back safely instead of taking the success path.
- Provider secret configuration stores only env-var names such as `OPENAI_API_KEY`; never persist or echo live secret values into `AITask.result_payload`, `error_message`, `fallback_reason`, or worker summaries.

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

Cancellation is a locked lifecycle transition:

- `POST /api/ai/tasks/{task_id}/cancel/` must call `cancel_owned_ai_task(...)` after authenticated owner lookup.
- Missing and wrong-owner task IDs are owner-scoped 404s; do not expose whether another user owns the task.
- Only `pending` tasks are user-cancellable. `running` tasks must keep their reservation and continue through the normal worker terminal path.
- Pending billable tasks release a still-reserved wallet reservation through `cancel_billable_ai_task(...)`.
- Terminal tasks are no-ops and return the existing task payload without another release or settlement.

Anti-abuse boundary:

- Once an AI task becomes `running`, provider work or billable fallback work may already have started. Do not let user cancellation convert that task to `cancelled`, clear its lease, or release funds early.
- A claimed `running` task must run to its terminal worker path and persist the resulting user-owned data row(s), such as a `WritingScore`, report payload, or learner-profile update.
- Product data writers such as `writing_score` must still ignore late completion/fallback for a legitimately cancelled `pending` task, because that task never entered billable execution.

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
- Claimed unsupported tasks must not stay `running`. The worker may report them as batch-level `skipped`, but it must still terminal-fail the row and release any reservation through the same billing-aware failure helper.

`settle_usage(...)` may return `pending_reconciliation` when authoritative usage is missing. The AI task can still succeed, but later reconciliation must use the same `call_id` idempotency.

Usage event audit contract:

- `CodexUsageEvent` keeps durable `provider` / `model` columns plus a JSON `metadata` field for settlement-time audit context.
- Billable AI success settlement must stamp usage metadata with:
  - `task_id`
  - `task_type`
  - effective `provider`
  - effective `model`
  - `prompt_version`
- Writing score settlement should also record `related_type`, `related_id`, and request identifiers such as `entry_id` and `prompt_id` when they exist.
- Backward-compatible callers outside the AI task flow may omit audit metadata; usage capture must still succeed with the historical defaults and an empty metadata object.

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
- Claimed work: choose the provider adapter from durable task fields (`task_type`, `provider`, `model`, `metadata`) instead of frontend memory or transient worker flags.
- Unknown or disabled writing providers should deterministically fall back through the same writing fallback path; unsupported task types still use the batch-level `skipped` summary plus terminal failure in the database.

Writing polling bridge:

- `GET /api/writing/entries/{entry_id}` returns the latest `ai_task` for the authenticated owner's entry by `task_type=writing_score`, `related_type=writing_entry`, and `related_id=entry_id`.
- The bridge is read-only; it must not infer score state from frontend memory or create/complete tasks during polling.
- A cancelled score task keeps the entry unscored. Late completion or fallback for a cancelled task must not create `WritingScore` or update the learner profile.

---

## Common Mistakes

- Creating a billable task without an `idempotency_key`; this risks duplicate wallet reservations.
- Settling or releasing wallet reservations outside `apps.ai.orchestration`; this decouples wallet and task terminal state.
- Treating `fallback` as success; it is terminal and releases billing, but it means default output was used.
- Failing stale `running` tasks immediately; recovery should requeue while `attempt_count < max_attempts`.

## Sample Databases

- Runtime SQLite stays at `backend_django/db.sqlite3` for local development.
- If a SQLite database is intentionally committed for demos or handoff, add a
  separate clearly named copy such as `backend_django/ielts_demo_sample.sqlite3`
  so reviewers can distinguish sample data from an unintentional local runtime
  database snapshot.
