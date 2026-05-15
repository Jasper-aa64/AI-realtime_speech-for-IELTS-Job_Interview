# Milestone 05 - Writing Score Task Completion Services

## Goal

Add worker-callable service functions that can complete or fallback a writing score task while updating writing score records, learner profile state, AI task status, and wallet billing state consistently.

## Scope

Included:

* Refactor writing score persistence into a reusable `persist_score` helper.
* Add `complete_score_task` for successful worker completion.
* Add `fallback_score_task` for default scoring when AI generation fails.
* Settle wallet reservation and link usage on successful completion.
* Release wallet reservation on fallback.
* Preserve the existing synchronous `/score` endpoint by reusing the same persistence helper.
* Add tests for success completion and fallback completion.

Excluded:

* No public worker endpoint yet.
* No Celery worker yet.
* No real AI provider adapter yet.
* No frontend cutover yet.
* No speaking task completion path yet.

## Files Changed

* `backend_django/apps/writing/services.py`
* `backend_django/apps/writing/tests.py`
* `.trellis/tasks/05-14-django-migration-architecture/milestone-05-writing-score-task-completion.md`

## Design Decisions

* Completion services are kept in Python service layer first. This avoids exposing unsafe public worker endpoints before authentication and deployment boundaries are settled.
* `complete_score_task` requires structured score fields and writes a normal `WritingScore`.
* `fallback_score_task` writes the same explicit default feedback style as current fallback behavior and releases reserved balance.
* Existing synchronous scoring still works and now shares the same `persist_score` path as future async completion.
* Billing settlement happens through the AI orchestration layer so task status and wallet state stay coupled.

## Verification Run

Passed:

* `python3 -m py_compile backend_django/apps/writing/services.py backend_django/apps/writing/tests.py`
* `.venv-django/bin/python backend_django/manage.py test apps.writing -v 2`
  * Result: `Ran 9 tests ... OK`
* `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py backend_django/manage.py $(find backend_django/apps -maxdepth 2 -name '*.py' -print)`
* `node --check web/static/app.js`
* `.venv-django/bin/python backend_django/manage.py check`
  * Result: `System check identified no issues (0 silenced).`
* `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
  * Result: `No changes detected`
* `.venv-django/bin/python backend_django/manage.py test -v 1`
  * Result: `Ran 45 tests ... OK`

## Known Gaps

* The completion functions are not yet connected to a worker command or Celery task.
* There is no worker authentication model because no worker HTTP endpoint exists yet.
* The frontend still uses the old synchronous score path.
* The speaking report flow still lacks equivalent async task completion.

## Rollback / Compatibility Notes

The old web app is unchanged. The existing Django `/score` endpoint remains compatible. If this milestone is rolled back, remove the new completion functions and related tests; the synchronous fallback scoring logic can be restored from the previous inline persistence block.

## Next Recommended Milestone

Milestone 06 should add an internal worker runner boundary:

* a management command or service entrypoint that claims pending `AITask` rows;
* a writing-score worker adapter that calls the current fallback implementation first, then later a real AI provider;
* worker lease/timeout handling;
* tests proving a pending task can be claimed and completed without browser state.
