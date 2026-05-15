# Stage: Writing Reports API Bridge

## Scope

- Added dedicated Django `GET /api/writing/reports`.
- Moved the old frontend `写作报告` list loader from `/api/writing/summary` to `/api/writing/reports`.
- Kept `GET /api/writing/summary`, entry detail reads, score-task polling, and worker flow unchanged.

## Changed Files

- `backend_django/apps/writing/services.py`
- `backend_django/apps/writing/views.py`
- `backend_django/apps/writing/tests.py`
- `backend_django/config/urls.py`
- `web/static/app.js`
- `backend_django/README.md`

## Validation

- Passed: `.venv-django/bin/python backend_django/manage.py test apps.writing.tests`
- Passed: `node --check web/static/app.js`
- Passed: `.venv-django/bin/python backend_django/manage.py check`
- Passed: `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
- Passed: `python3 -m py_compile web/ielts_server.py`

## Rollback

- Remove `/api/writing/reports` route and service.
- Point `loadWritingReports()` back to `/api/writing/summary`.
- Re-run the targeted writing tests and JS syntax check.

## Next Stage

- If needed later, reduce report-page detail fetch fan-out by using the compact report list payload directly for the left rail before hydrating selected entry detail.
