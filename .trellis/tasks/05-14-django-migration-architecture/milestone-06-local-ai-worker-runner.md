# Milestone 06 - Local AI Worker Runner

## Goal

Add a local worker boundary that can claim pending AI tasks and complete a writing score task without relying on browser state. This proves the lifecycle before introducing Celery/Redis.

## Scope

Included:

* Add `python backend_django/manage.py run_ai_tasks --limit N`.
* Claim available pending `AITask` rows in created order.
* Process `writing_score` tasks through the current fallback adapter.
* Reuse `fallback_score_task`, so writing score records, learner profiles, task status, and wallet release happen through the same tested service path.
* Add a regression test that creates a writing score task, runs the command, and verifies fallback completion plus wallet release.
* Document the command in `backend_django/README.md`.

Excluded:

* No Celery or Redis worker yet.
* No real AI provider adapter yet.
* No long-running daemon mode yet.
* No public worker HTTP endpoint.
* No speaking task runner yet.

## Files Changed

* `backend_django/apps/ai/management/__init__.py`
* `backend_django/apps/ai/management/commands/__init__.py`
* `backend_django/apps/ai/management/commands/run_ai_tasks.py`
* `backend_django/apps/ai/tests.py`
* `backend_django/README.md`
* `.trellis/tasks/05-14-django-migration-architecture/milestone-06-local-ai-worker-runner.md`

## Design Decisions

* A management command is safer than a public worker endpoint at this stage because worker authentication and deployment boundaries are not settled.
* The command runs once and exits. A scheduler, Celery worker, or process manager can call the same service path later.
* The first adapter intentionally uses fallback so the lifecycle can be verified without a real AI provider key.
* Unsupported task types are skipped instead of failed so future task types can be added incrementally.

## Verification Run

Passed:

* `python3 -m py_compile backend_django/apps/ai/management/commands/run_ai_tasks.py backend_django/apps/ai/tests.py`
* `.venv-django/bin/python backend_django/manage.py test apps.ai -v 2`
  * Result: `Ran 18 tests ... OK`
* `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py backend_django/manage.py $(find backend_django/apps -maxdepth 4 -name '*.py' -print)`
* `node --check web/static/app.js`
* `.venv-django/bin/python backend_django/manage.py check`
  * Result: `System check identified no issues (0 silenced).`
* `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
  * Result: `No changes detected`
* `.venv-django/bin/python backend_django/manage.py test -v 1`
  * Result: `Ran 46 tests ... OK`

## Known Gaps

* The worker currently falls back rather than calling a real provider.
* No lease timeout recovery exists for tasks stuck in `running`.
* No cancellation flow exists.
* No Redis/Celery process exists.
* No frontend uses this flow yet.

## Rollback / Compatibility Notes

The command is additive and does not affect the legacy app. Removing it would not alter the existing synchronous writing score endpoint or Django task creation endpoints.

## Next Recommended Milestone

Milestone 07 should add worker lease recovery and cancellation:

* recover `running` tasks whose `started_at` is too old;
* add service tests for stuck worker recovery;
* add cancellation/release behavior for pending tasks;
* then decide whether to introduce Celery/Redis or first bridge the frontend to `/score-task` polling.
