# Milestone 02 - AI Task Lifecycle Foundation

## Goal

Create the durable AI task lifecycle foundation needed for refresh-safe scoring/report generation, duplicate-submit protection, retry tracking, fallback visibility, and future Celery/Redis worker execution.

## Scope

Included:

* Extend `AITask` with stable identifiers, idempotency, progress, retry, timestamps, error state, request/result payloads, and billing links.
* Add `AITask` service functions for create, claim, progress, success, retry/fail, fallback, and user-scoped lookup.
* Add minimal authenticated API endpoints for creating and reading AI tasks.
* Add tests for idempotency, user isolation, lifecycle transitions, retry exhaustion, fallback state, payload shape, and API behavior.
* Add a migration with task-id backfill for pre-existing rows.
* Update admin and README.

Excluded:

* No Celery worker process yet.
* No Redis configuration yet.
* No real provider execution inside the AI task service yet.
* No legacy frontend integration yet.
* No changes to the current old web app behavior.

## Files Changed

* `backend_django/apps/ai/models.py`
* `backend_django/apps/ai/services.py`
* `backend_django/apps/ai/views.py`
* `backend_django/apps/ai/admin.py`
* `backend_django/apps/ai/tests.py`
* `backend_django/apps/ai/migrations/0002_aitask_attempt_count_aitask_available_at_and_more.py`
* `backend_django/config/urls.py`
* `backend_django/README.md`

## Design Decisions

* `AITask.task_id` is the public stable ID used by clients after refresh.
* `idempotency_key` is unique and user-checked so repeated submit returns the existing task, while cross-user reuse is rejected.
* `call_id` remains available to link legacy Codex billing usage and future provider calls.
* `request_payload` and `result_payload` keep enough state for retry and reload without relying on a still-open browser page.
* `attempt_count`, `max_attempts`, `available_at`, and `worker_id` prepare the model for worker claiming and retry scheduling.
* `fallback` is a terminal status distinct from `failed`, so default suggestions cannot be mistaken for successful AI output.
* The service layer is synchronous now. Celery should later call this same service layer rather than duplicating state transitions in worker code.

## Verification Run

Passed:

* `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py backend_django/manage.py backend_django/apps/ai/models.py backend_django/apps/ai/services.py backend_django/apps/ai/views.py backend_django/apps/ai/tests.py`
* `node --check web/static/app.js`
* `.venv-django/bin/python backend_django/manage.py check`
  * Result: `System check identified no issues (0 silenced).`
* `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
  * Result: `No changes detected`
* `.venv-django/bin/python backend_django/manage.py test apps.ai -v 2`
  * Result: `Ran 10 tests ... OK`
* `.venv-django/bin/python backend_django/manage.py test -v 1`
  * Result: `Ran 35 tests ... OK`

## Known Gaps

* There is no worker loop yet; task claiming is implemented as a service function, not connected to Celery.
* There is no task cancellation endpoint yet.
* Billing reservation and usage links are model-level ready, but report/scoring APIs do not yet create reservations through `AITask`.
* The old frontend does not yet create or poll Django AI tasks.
* Existing legacy `web/ielts_server.py` still runs AI calls synchronously.

## Rollback / Compatibility Notes

The old app is unaffected because no `web/` runtime behavior changed. Django migration `ai.0002` adds nullable fields and backfills `task_id` for existing AI task rows. If rollback is needed before production data, the migration can be unapplied; after production data, export task state first because `request_payload` / `result_payload` may contain recoverability metadata.

## Next Recommended Milestone

Milestone 03 should connect AI tasks to billing and product flows:

* introduce a task orchestration service for writing score and speaking report jobs;
* reserve wallet balance when a task is created;
* settle/release reservation when the task succeeds, fails, or falls back;
* expose refresh-safe task status to the writing/speaking APIs;
* keep actual Celery integration optional until orchestration is covered by tests.
