# Milestone 03 - Billable AI Task Orchestration

## Goal

Connect durable AI task state to wallet reservation/settlement so future writing and speaking scoring jobs can survive refreshes, avoid duplicate submits, and avoid double charging.

## Scope

Included:

* Add a billable AI orchestration service that reserves wallet balance at task creation.
* Reuse `AITask` lifecycle service functions for claim/progress/success/fail/fallback.
* Settle wallet usage on successful task completion.
* Release wallet reservation on fallback or final failure.
* Keep retryable task state and billing reservation together so retries do not require a new charge.
* Let `POST /api/ai/tasks/` create either a plain task or a billable task when `reserved_u` is provided.
* Add tests for reservation idempotency, cross-user protection, success settlement, fallback release, final failure release, invalid reservation input, and billable API behavior.

Excluded:

* No Celery process yet.
* No Redis broker yet.
* No provider execution adapter yet.
* No writing/speaking endpoint cutover yet.
* No old frontend integration yet.

## Files Changed

* `backend_django/apps/ai/orchestration.py`
* `backend_django/apps/ai/views.py`
* `backend_django/apps/ai/tests.py`
* `backend_django/README.md`
* `.trellis/tasks/05-14-django-migration-architecture/milestone-03-billable-ai-task-orchestration.md`

## Design Decisions

* Billable AI tasks require an `idempotency_key`. This prevents duplicate browser clicks from creating multiple charges.
* `call_id` is generated from the user and idempotency key when not supplied. This aligns AI task identity with billing reservation identity.
* Reservation happens before the task is created. If balance is insufficient, no task is created.
* Fallback is treated as a terminal non-charged result and releases reserved balance.
* Final failure releases reserved balance. Retryable non-terminal failure keeps the reservation.
* The orchestration service is deliberately independent from Celery so workers can call the same tested state transitions later.

## Verification Run

Passed:

* `python3 -m py_compile backend_django/apps/ai/orchestration.py backend_django/apps/ai/views.py backend_django/apps/ai/tests.py`
* `.venv-django/bin/python backend_django/manage.py test apps.ai -v 1`
  * Result: `Ran 17 tests ... OK`
* `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py backend_django/manage.py $(find backend_django/apps/ai -maxdepth 1 -name '*.py' -print)`
* `node --check web/static/app.js`
* `.venv-django/bin/python backend_django/manage.py check`
  * Result: `System check identified no issues (0 silenced).`
* `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
  * Result: `No changes detected`
* `.venv-django/bin/python backend_django/manage.py test -v 1`
  * Result: `Ran 42 tests ... OK`

## Known Gaps

* `writing.score_entry` and speaking report generation still run through their current synchronous/fallback flows; they do not yet create billable Django `AITask` rows.
* There is no task cancellation endpoint.
* There is no worker lease timeout recovery yet.
* Celery/Redis is still a planned execution layer, not an installed dependency.
* The API exposes task creation/status but not an explicit claim/complete endpoint for workers; those are service-layer only for now.

## Rollback / Compatibility Notes

The old app is unaffected. The new orchestration code only changes Django-side `api/ai/tasks/` behavior when callers opt in with `reserved_u`. Existing plain task creation remains supported.

## Next Recommended Milestone

Milestone 04 should bridge one product flow to this framework without taking over everything:

* start with writing scoring because it is simpler than realtime speaking;
* add an async/billable writing score task creation path;
* keep the existing synchronous fallback score endpoint working;
* expose refresh-safe polling for the writing entry's active AI task;
* verify that duplicate clicks return the same task and do not double reserve.
