# Milestone 00 - Planning Context And Execution Gate

## Goal

Move the Django migration task from loose planning into Trellis-managed execution by persisting architecture decisions, curating subtask context, and defining the first implementation target.

## Scope

Included:

* Capture durable architecture decisions for Django, Celery/Redis, Channels, C++ service boundaries, and frontend migration timing.
* Keep the current legacy web app untouched.
* Prepare `implement.jsonl` and `check.jsonl` for Trellis execution.
* Start the Trellis task once context is complete.

Excluded:

* No real payment, SMS, or WeChat provider integration.
* No destructive database operation.
* No Vue migration.
* No C++ rewrite in this milestone.

## Files Changed

* `.trellis/tasks/05-14-django-migration-architecture/prd.md`
* `.trellis/tasks/05-14-django-migration-architecture/research/architecture-decisions.md`
* `.trellis/tasks/05-14-django-migration-architecture/milestone-00-planning-context.md`
* `.trellis/tasks/05-14-django-migration-architecture/implement.jsonl`
* `.trellis/tasks/05-14-django-migration-architecture/check.jsonl`

## Design Decisions

* Django is the business state owner.
* Redis/Celery is the target for recoverable background execution.
* Channels is reserved for WebSocket/live status needs after HTTP status polling proves insufficient.
* C++ is reserved for speech processing and low-latency audio service work, not business records or billing.
* Existing vanilla frontend remains usable while Django APIs stabilize.

## Verification Run

Completed:

* `python3 ./.trellis/scripts/task.py current --source`
* `python3 ./.trellis/scripts/task.py start .trellis/tasks/05-14-django-migration-architecture`
* `sed -n '1,120p' .trellis/tasks/05-14-django-migration-architecture/implement.jsonl`
* `sed -n '1,120p' .trellis/tasks/05-14-django-migration-architecture/check.jsonl`

Result:

* Current task was set to `.trellis/tasks/05-14-django-migration-architecture`.
* Status changed from `planning` to `in_progress`.
* `implement.jsonl` and `check.jsonl` now contain real spec/research entries instead of only the seed `_example` row.

Milestone 01 verification then ran:

* `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py`
* `node --check web/static/app.js`
* `.venv-django/bin/python backend_django/manage.py check`
* `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
* `.venv-django/bin/python backend_django/manage.py test`

## Known Gaps

* The current task has many unrelated dirty files from previous work; this milestone does not classify or commit them.
* Django dependencies may need installation into `.venv-django`.
* The existing Trellis backend/frontend spec files are still partly template-like and need later refinement.

## Rollback / Compatibility Notes

This milestone only changes Trellis task documentation and context files. It does not change runtime code paths and should not affect the legacy web app.

## Next Recommended Milestone

Milestone 01 should stabilize the Django scaffold already present under `backend_django/`: install/check dependencies, run migrations/tests, fix model/API/test defects, and document the verified state.
