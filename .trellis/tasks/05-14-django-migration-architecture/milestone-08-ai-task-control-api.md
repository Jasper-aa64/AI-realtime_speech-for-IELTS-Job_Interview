# Milestone 08 - AI Task Control API and Writing Polling Bridge

## Goal

Expose an authenticated Django-side cancel API for durable AI tasks and make
the writing score polling bridge safe across refresh, cancellation, and late
worker callbacks.

## Scope

Included:

* add `POST /api/ai/tasks/{task_id}/cancel/` with authenticated owner-only access;
* route billable cancellation through `cancel_billable_ai_task()` so wallet reservations release idempotently;
* keep non-billable and terminal-task cancellation safe and payload-compatible;
* keep `GET /api/writing/entries/{entry_id}` returning the latest `ai_task` state for score polling;
* harden writing score completion/fallback services so cancelled tasks do not create `WritingScore` rows on late callbacks;
* add focused tests for cancel auth/ownership, pending and running billable cancellation, writing entry polling after cancel, and worker skip behavior for cancelled tasks;
* update backend API docs.

Excluded:

* no legacy `web/` bridge changes;
* no Celery/Redis integration yet;
* no speaking async task bridge yet;
* no new database schema or migration.

## Files Changed

* `backend_django/apps/ai/orchestration.py`
* `backend_django/apps/ai/views.py`
* `backend_django/apps/ai/management/commands/run_ai_tasks.py`
* `backend_django/apps/ai/tests.py`
* `backend_django/apps/writing/services.py`
* `backend_django/apps/writing/tests.py`
* `backend_django/config/urls.py`
* `backend_django/README.md`
* `.trellis/tasks/05-14-django-migration-architecture/milestone-08-ai-task-control-api.md`

## Design Decisions

* The cancel route stays generic under `/api/ai/tasks/` instead of adding a writing-specific cancel endpoint. That keeps ownership, billing release, and terminal-state semantics in one place.
* Owner checks happen before task cancellation is dispatched. Wrong-owner and missing IDs both return `404 AI task not found`.
* Billable and non-billable cancellation still use the existing service/orchestration helpers. The new API only exposes the already-tested lifecycle path.
* Writing completion and fallback now lock the `AITask` row first and return the current entry payload immediately for terminal tasks. This preserves the milestone-07 late-success billing fix and extends it to writing data, preventing cancelled tasks from inventing `WritingScore` or learner-profile updates.
* `run_ai_tasks` now treats a task that becomes cancelled before claim, or after claim but before fallback persistence, as cancelled/skipped in the worker summary instead of surfacing an execution error or a false fallback completion.

## Verification

Implementation and follow-up validation checks were run on 2026-05-15:

* `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py backend_django/manage.py $(find backend_django/apps -maxdepth 4 -name '*.py' -print)`
  * Result: passed
* `node --check web/static/app.js`
  * Result: passed
* `.venv-django/bin/python backend_django/manage.py check`
  * Result: `System check identified no issues (0 silenced).`
* `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
  * Result: `No changes detected`
* `.venv-django/bin/python backend_django/manage.py test -v 1`
  * Result: `Ran 61 tests ... OK`

## Known Gaps

* Re-submitting `/score-task` for the same unchanged answer after cancellation still returns the existing cancelled task because the idempotency key is answer-based. A later milestone can decide whether cancelled tasks should be restartable with the same answer.
* `run_ai_tasks` still executes only the fallback writing adapter; there is no real AI provider path yet.
* There is still no push status channel; refresh-safe polling remains HTTP-based.

## Rollback

This milestone is additive to the Django scaffold and does not touch the legacy
`web/` runtime. Rolling back means removing the cancel route and the writing
task terminal-state guard code, then re-running the Django test suite. No
schema rollback is required because no migration was added.

## Next Milestone

Milestone 09 should choose one of the remaining execution-layer gaps:

* add a real worker/provider adapter for `writing_score` so successful async completion is exercised end-to-end; or
* add the first speaking/report task bridge once the writing async control path is considered stable.
