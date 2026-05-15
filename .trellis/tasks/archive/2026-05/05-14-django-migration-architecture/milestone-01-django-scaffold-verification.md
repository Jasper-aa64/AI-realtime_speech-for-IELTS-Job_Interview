# Milestone 01 - Django Scaffold Verification

## Goal

Verify that the existing Django scaffold is runnable from the repository root, that migrations are current, that the custom user model is active, that core admin registrations exist, and that tests are discoverable by the planned command.

## Scope

Included:

* Validate `.venv-django` dependency availability.
* Run legacy Python syntax check and frontend JavaScript syntax check.
* Run Django system check, migration dry run, migration plan, tests, and admin/user-model inspection.
* Fix the test discovery gap where `python backend_django/manage.py test` found 0 tests from the repository root.
* Update backend README commands to match the now-supported root invocation.

Excluded:

* No business API migration from the old server.
* No Celery/Redis implementation.
* No real payment, SMS, or WeChat provider integration.
* No C++ speech service code changes.
* No Vue migration.

## Files Changed

* `backend_django/manage.py`
* `backend_django/README.md`
* `.trellis/tasks/05-14-django-migration-architecture/milestone-01-django-scaffold-verification.md`

## Design Decisions

* `backend_django/manage.py` now changes the process working directory to its own directory before executing Django commands. This makes `python backend_django/manage.py test` discover app tests from the repository root, matching the project test plan.
* The README now documents root-level `manage.py` commands, so local setup does not depend on manually changing directories.
* No runtime product code was changed. The current legacy web app remains untouched.

## Verification Run

Passed:

* `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py backend_django/manage.py`
* `node --check web/static/app.js`
* `.venv-django/bin/python backend_django/manage.py check`
  * Result: `System check identified no issues (0 silenced).`
* `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
  * Result: `No changes detected`
* `.venv-django/bin/python backend_django/manage.py test -v 1`
  * Result: `Ran 25 tests ... OK`
* `.venv-django/bin/python backend_django/manage.py migrate --plan`
  * Result: `No planned migration operations.`
* Django shell inspection:
  * `AUTH_USER_MODEL accounts.CustomUser`
  * Core models were registered in Django admin.

Additional confirmation:

* Running from inside `backend_django/` still discovers and runs 25 tests.
* Running with explicit `apps` label also discovers and runs 25 tests.

## Known Gaps

* The current Trellis backend/frontend spec files are still partly template-like. They need a later spec cleanup milestone.
* The worktree contains many unrelated uncommitted changes from earlier work; this milestone does not classify or commit them.
* The Django scaffold has data models and basic APIs, but the long-running AI task queue is not implemented yet.
* Payment, SMS, WeChat binding, and production provider adapters are still placeholders or planned concepts.

## Rollback / Compatibility Notes

The only runtime-adjacent code change is `manage.py` setting its current working directory to `backend_django/`. This affects management command invocation only and makes root-level commands more deterministic. It does not affect the legacy `web/` server or frontend.

## Next Recommended Milestone

Milestone 02 should implement the recoverable AI task framework:

* extend `AITask` with durable lifecycle fields needed for retries, idempotency, progress, and billing linkage;
* add service functions for creating, claiming, succeeding, failing, and falling back tasks;
* add tests for refresh-safe task state and duplicate-submit protection;
* keep Celery/Redis integration behind an adapter or settings gate if introducing the actual worker is too large for the next step.
