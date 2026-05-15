# Milestone 04 - Writing Score Task Bridge

## Goal

Bridge one product flow to the durable AI task framework without breaking the existing synchronous writing scoring endpoint.

## Scope

Included:

* Add `POST /api/writing/entries/{entry_id}/score-task`.
* Create a billable `writing_score` AI task for a saved writing entry.
* Reserve wallet balance when the score task is created.
* Make duplicate clicks idempotent for the same entry answer by hashing the answer into the idempotency key.
* Include the latest writing score AI task in writing entry detail payloads so refresh/reload can recover task status.
* Keep `POST /api/writing/entries/{entry_id}/score` unchanged for the current fallback-compatible synchronous flow.
* Add regression tests for duplicate score-task submits, reservation behavior, and task visibility on entry detail.

Excluded:

* No worker execution of the score task yet.
* No frontend cutover to `/score-task` yet.
* No real AI provider call from Django yet.
* No speaking report task bridge yet.

## Files Changed

* `backend_django/apps/writing/services.py`
* `backend_django/apps/writing/views.py`
* `backend_django/apps/writing/tests.py`
* `backend_django/config/urls.py`
* `backend_django/README.md`
* `.trellis/tasks/05-14-django-migration-architecture/milestone-04-writing-score-task-bridge.md`

## Design Decisions

* The new `/score-task` endpoint is additive. The existing `/score` endpoint remains available and synchronous.
* The task idempotency key is `writing_score:{entry_id}:{answer_hash}`. This prevents double reservation for repeated clicks, while allowing a new task after the answer changes.
* Writing entry detail includes `ai_task` so the UI can poll/recover after refresh without relying on in-memory browser state.
* The default score-task reservation is `1_000_000` micro RMB, and callers can override it with `reserved_u`.

## Verification Run

Passed:

* `python3 -m py_compile backend_django/apps/writing/services.py backend_django/apps/writing/views.py backend_django/apps/writing/tests.py`
* `.venv-django/bin/python backend_django/manage.py test apps.writing -v 2`
  * Result: `Ran 7 tests ... OK`
* `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py backend_django/manage.py $(find backend_django/apps -maxdepth 2 -name '*.py' -print)`
* `node --check web/static/app.js`
* `.venv-django/bin/python backend_django/manage.py check`
  * Result: `System check identified no issues (0 silenced).`
* `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
  * Result: `No changes detected`
* `.venv-django/bin/python backend_django/manage.py test -v 1`
  * Result: `Ran 43 tests ... OK`

## Known Gaps

* The frontend still calls the old synchronous scoring behavior.
* There is no worker that consumes `writing_score` tasks.
* There is no task completion endpoint or provider adapter for writing scoring.
* There is no reservation release wired to browser-side cancellation yet.

## Rollback / Compatibility Notes

This milestone is additive. Removing the `/score-task` route and service function would leave the existing `/score` behavior intact. The old `web/` app was not modified.

## Next Recommended Milestone

Milestone 05 should add a worker-facing completion/cancellation surface:

* define internal endpoints or management commands for worker claim/success/fallback/fail;
* complete a writing score task by creating `WritingScore`, updating `WritingLearnerProfile`, settling billing, and marking the `AITask` succeeded;
* fallback a writing score task by releasing reservation and clearly marking fallback;
* keep all transitions idempotent.
