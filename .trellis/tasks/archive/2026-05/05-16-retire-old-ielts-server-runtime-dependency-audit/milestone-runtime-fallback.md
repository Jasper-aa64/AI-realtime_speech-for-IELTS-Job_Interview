# Stage: Django speaking runtime fallback endpoints

## Scope

- Added Django fallback-only runtime endpoints:
  - `POST /api/attempts/{attempt_id}/turns/{turn_id}/complete`
  - `POST /api/attempts/{attempt_id}/abort`
  - `POST /api/attempts/{attempt_id}/score`
- Fixed Django audio upload compatibility with the current browser raw Blob
  request body.
- Kept frontend unchanged and kept `web/ielts_server.py` in place.

## Dependency Audit

### Django-owned runtime/API surface

- Accounts: `/api/accounts/*`
- Writing: `/api/writing/*`
- Billing: `/api/billing/*`
- AI tasks: `/api/ai/tasks/*`
- Speaking history/report/delete: `/api/history`, `/api/history/{id}`
- Speaking question bank/training reads:
  `/api/question-bank/summary`, `/api/question-bank/sample`,
  `/api/training/weak-items`, `/api/training/replay-queue`
- Speaking runtime skeleton:
  `/api/attempts/start`,
  `/api/attempts/{id}/turns/{turn_id}/audio`,
  `/api/audio/{id}/{turn_id}/candidate`
- Speaking runtime fallback added in this stage:
  `/api/attempts/{id}/turns/{turn_id}/complete`,
  `/api/attempts/{id}/abort`,
  `/api/attempts/{id}/score`

### Still old-server/provider-heavy or blocked

- `POST /api/tts` - requires TTS provider/storage cutover.
- `POST /api/p3/questions` and `/api/p3/follow-up` - provider-backed P3
  generation still needs a separate fallback/provider strategy.
- Regenerate endpoints:
  `/api/attempts/{id}/turns/{turn_id}/feedback/regenerate`,
  `/api/attempts/{id}/turns/{turn_id}/transcript/regenerate`.
- Static frontend serving and fallback runtime behavior remain on
  `web/ielts_server.py` until deployment/cutover is explicit.

## Changed Files

- `backend_django/apps/speaking/services.py`
- `backend_django/apps/speaking/views.py`
- `backend_django/apps/speaking/tests.py`
- `backend_django/config/urls.py`

## Validation

- Passed: `.venv-django/bin/python backend_django/manage.py test apps.speaking.tests`
- Passed: `.venv-django/bin/python backend_django/manage.py test`
- Passed: `.venv-django/bin/python backend_django/manage.py check`
- Passed: `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
- Passed: `node --check web/static/app.js`

## Rollback

- Remove the three new Django runtime routes and service functions.
- Revert raw Blob compatibility change only if old server remains the sole
  browser audio upload handler.
- Re-run speaking tests and JS syntax check.

## Next Stage

- Do not delete `web/ielts_server.py` yet.
- Plan and implement provider-light fallbacks for P3 generation and regenerate
  endpoints only after reviewing frontend usage.
- TTS and real transcript regeneration require provider/storage configuration
  and should remain separate tasks.
