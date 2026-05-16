# Stage: Feature-flagged Django speaking runtime cutover

## Scope

- Added `IELTS_DJANGO_PROXY_SPEAKING_RUNTIME` to `web/ielts_server.py`.
- When enabled and a `sessionid` cookie is present, the old server proxies only
  migrated speaking runtime endpoints to Django:
  - `POST /api/attempts/start`
  - `POST /api/attempts/{id}/turns/{turn_id}/audio`
  - `POST /api/attempts/{id}/turns/{turn_id}/complete`
  - `POST /api/attempts/{id}/score`
  - `POST /api/attempts/{id}/abort`
  - `GET /api/audio/{id}/{turn_id}/candidate`
- Added raw-body proxying for browser audio uploads.
- Kept fallback to old server when the flag is off, no session cookie exists, or
  Django is unavailable.

## Explicit Non-Scope

- No frontend changes.
- No TTS migration.
- No P3 generation migration.
- No regenerate endpoint migration.
- No billing/provider changes.
- No deletion or freezing of `web/ielts_server.py`.

## Changed Files

- `web/ielts_server.py`
- `tests/test_ielts_web_server.py`

## Validation

- Passed: `python3 -m pytest tests/test_ielts_web_server.py -q`
- Passed: `python3 -m py_compile web/ielts_server.py`
- Passed: `.venv-django/bin/python backend_django/manage.py test apps.speaking.tests`
- Passed: `.venv-django/bin/python backend_django/manage.py test`
- Passed: `.venv-django/bin/python backend_django/manage.py check`
- Passed: `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
- Passed: `node --check web/static/app.js`

## Rollback

- Set `IELTS_DJANGO_PROXY_SPEAKING_RUNTIME=0`, or revert the flag and raw proxy
  changes. Old server fallback handlers remain intact.

## Remaining Old-Server Dependencies

- Static frontend serving.
- TTS: `/api/tts` and `/api/tts-audio/*`.
- P3 generation: `/api/p3/questions`, `/api/p3/follow-up`.
- Regenerate endpoints:
  `/api/attempts/{id}/turns/{turn_id}/feedback/regenerate`,
  `/api/attempts/{id}/turns/{turn_id}/transcript/regenerate`.
