# Speaking Report Lifecycle Design

## Scope

Decouple the persisted speaking practice record from the optional AI-generated report. A completed Attempt is a history record before scoring begins; AI task state only changes its report status.

## State derivation

`report_services.py` will expose one internal lifecycle resolver used by both history and detail:

1. A valid persisted `SpeakingReport` with a scored Attempt is `ready`.
2. Otherwise, the newest related speaking-report task in `pending` or `running` is `scoring`.
3. Otherwise, a terminal task or persisted analysis failure is `failed`.
4. Otherwise, a completed non-aborted Attempt is `unscored`.
5. An in-progress or aborted Attempt without a completed marker is not a report-history item.

The resolver must never use frontend state, localStorage, or task creation as a prerequisite for visibility. The list and detail serializers will use the same state and preserve the Attempt's turns/audio/transcript in all non-ready states.

## Task transitions

The existing score endpoint remains the only task creation boundary. It keeps idempotency by Attempt/transcript hash, returns an existing active task, and creates a new task only after a terminal failure when the user explicitly retries. Success updates the same Attempt and creates/updates its single report. Terminal worker errors update the same Attempt metadata and task; no source rows are deleted.

## Error presentation

The backend will map recognizable provider failures to learner-readable messages: insufficient balance (including upstream 403), authentication (401), forbidden access (403), timeout, output truncation, and malformed/parse failure. The raw task error remains available in the task payload for diagnostics, but the user sees an actionable explanation and a manual retry path.

## Frontend behavior

The report rail, manager, detail view, retry control, and polling use explicit backend `report_status` values. `scoring` never renders a regenerate button. History loading may start a poll from the persisted `ai_task.id`, but cached or in-memory values can only improve repaint timing; they cannot create or hide a report. Terminal polling refreshes history/detail from the backend.

## Regression coverage

Backend tests cover no-task completed attempts, pending/running, failed 403 balance, success, refresh-equivalent repeated API reads, deletion isolation, and list/detail parity. Frontend static tests cover distinct status labels, central predicates, and no regenerate control in scoring markup. Existing tests for worker/provider behavior remain unchanged.

## Non-goals

No migration, Band change, AI execution, automatic retry, worker start, tunnel restart, or public URL change.
