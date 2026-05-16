# Django-only runtime cutover record

## Scope

This task closes the remaining local runtime contracts needed for Django to run
the IELTS web app without using `web/ielts_server.py` for business traffic.

## Completed

* Django serves the frontend entrypoints:
  * `/`
  * `/index.html`
  * `/app.js`
  * `/styles.css`
* Django covers fallback speaking runtime surfaces:
  * `POST /api/p3/questions`
  * `POST /api/p3/follow-up`
  * `POST /api/tts`
  * `GET /api/tts-audio/{role}/{filename}`
  * `GET /api/reports/latest`
* Django supports frontend billing paths with and without trailing slashes.
* Frontend runtime API calls in `web/static/app.js` are covered by Django URLs.

## Non-goals

* Do not delete `web/ielts_server.py`.
* Do not integrate real Azure Speech, Codex/OpenAI scoring, or Volcengine TTS.
* Do not change production static asset strategy.

## Validation

* `backend_django/manage.py test apps.billing.tests apps.speaking.tests`
* `backend_django/manage.py test`
* `backend_django/manage.py check`
* `backend_django/manage.py makemigrations --check --dry-run`
* `node --check web/static/app.js`
* `python3 -m py_compile web/ielts_server.py`
* `python3 -m pytest tests/test_ielts_web_server.py -q`
