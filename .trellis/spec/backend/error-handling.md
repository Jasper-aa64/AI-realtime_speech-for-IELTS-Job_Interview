# Error Handling

> Error and terminal-state contracts for Django backend services.

---

## Overview

Backend views should translate service errors into small JSON responses, while services own validation, locking, and lifecycle decisions.

AI task errors use:

- `AITaskError`: generic lifecycle/service validation errors.
- `AIOrchestrationError`: billing-aware AI task orchestration errors.
- `BillingError`: wallet reservation, settlement, and usage validation errors.

Do not leak tracebacks or provider internals to clients. Return the service message as `{"error": "<message>"}` with the appropriate status.

---

## API Error Responses

Current AI task endpoints use these response contracts:

- Unauthenticated request: `401 {"error": "authentication required"}`.
- `POST /api/ai/tasks/` validation/orchestration error: `400 {"error": "<message>"}`.
- `GET /api/ai/tasks/{task_id}` missing or wrong-owner task: `404 {"error": "AI task not found"}`.
- `POST /api/ai/tasks/{task_id}/cancel/` requires auth, uses owner-scoped lookup, returns `404 {"error": "AI task not found"}` for missing or wrong-owner tasks, returns `409 {"error": "AI task is already running and cannot be cancelled"}` for `running` tasks, and returns the task payload on success or terminal no-op.

`read_json_body()` treats malformed or non-object JSON as `{}`. Required field validation must happen in the service layer so empty payloads become deterministic service errors such as `task_type is required`.

---

## Lifecycle Error Matrix

| Condition | Service behavior | Client/worker result |
|---|---|---|
| Missing `task_type` | `create_ai_task` raises `AITaskError("task_type is required")` | POST returns 400 |
| Billable task missing `idempotency_key` | `create_billable_ai_task` raises `AIOrchestrationError` | POST returns 400 |
| `reserved_u` missing, zero, negative, or non-integer for billable task | `AIOrchestrationError("reserved_u must be a positive integer")` | POST returns 400 |
| Insufficient wallet balance | `BillingError` is wrapped as `AIOrchestrationError` | POST returns 400, no task created |
| Same idempotency key, same user | Return existing task with `created=false` | POST returns 200 |
| Same idempotency key, different user | Raise ownership error | POST returns 400 |
| Cancel missing or wrong-owner task | `cancel_owned_ai_task` raises `AITaskError("AI task not found")` | POST cancel returns owner-scoped 404 |
| Cancel pending task | Mark `cancelled`; release reserved wallet funds when billable | POST cancel returns task payload |
| Cancel running task | `cancel_ai_task`, `cancel_billable_ai_task`, and `cancel_owned_ai_task` propagate `AITaskConflictError("AI task is already running and cannot be cancelled")` | POST cancel returns 409; worker keeps running and keeps any reservation |
| Cancel terminal task | Return unchanged task | POST cancel returns existing task payload |
| Task claim from non-`pending` status | `claim_ai_task` raises `AITaskError` | Worker records item error |
| `available_at` is in the future | `claim_ai_task` raises `AITaskError` | Worker leaves task untouched |
| Stale recovery timeout <= 0 | `stale_running_task_ids` raises `AITaskError` | Caller must reject/fix config |
| Late success/fail/fallback/cancel after terminal state | Return task unchanged | No double settlement/release |

---

## Terminal Callback Safety

All terminal callbacks must be idempotent:

- `succeed_ai_task`, `fail_ai_task`, `fallback_ai_task`, and `cancel_ai_task` return immediately when `task.is_terminal`.
- `succeed_billable_ai_task` checks terminal state before settlement.
- Billing fallback/fail/cancel helpers call the generic transition first and only release if the resulting status is the intended terminal status.

This protects against late provider callbacks, duplicate worker retries, and user cancellation racing with worker completion.

Writing score callbacks must extend the same rule to product data: when a `writing_score` task is already `cancelled`, late completion or fallback returns the current entry payload, leaves the entry unscored, and must not create `WritingScore`.
When a `writing_score` task is already `running`, user cancellation must fail fast instead of changing task state; later completion/fallback must continue to persist the score/profile output against that same task.

---

## Worker Recovery Errors

`run_ai_tasks --recover-stale-seconds N` invokes billing-aware stale recovery before claiming pending work.

Recovery behavior:

- Stale `running` task with attempts remaining: set `pending`, reset progress to `0`, clear worker/timing fields, preserve reservation.
- Stale `running` task with exhausted attempts: set `failed`, clear worker, set `finished_at`, release reservation if billable.
- Terminal task discovered during recovery: return unchanged.

The command emits a JSON summary. Worker errors should be recorded per item instead of crashing the whole batch where possible.

If `run_ai_tasks` sees a task cancelled before claim, it should skip the item and avoid creating product rows. If a cancel request arrives after claim, that request must fail with a conflict so the worker can finish and persist the normal fallback/result path.

---

## Common Mistakes

- Returning `500` for expected validation failures; lifecycle and billing validation should map to 400.
- Releasing a reservation on retryable failure; only final failure, fallback, and cancellation release.
- Running terminal callbacks without first checking `task.is_terminal`; this can double charge or double release.
- Treating wrong-owner task lookup as authorization detail; respond as not found.
