# Finalize Django-only IELTS runtime cutover

## Goal

Close the remaining Django-only runtime gaps so `backend_django` can serve the
web frontend and all frontend-visible API contracts without relying on
`web/ielts_server.py` as a business runtime.

## Review Findings

* Django already owns the main speaking/writing/account/billing runtime.
* Remaining Django gaps found during review:
  * Static frontend root and `/app.js`/`/styles.css` serving.
  * `/api/p3/questions` and `/api/p3/follow-up`.
  * `/api/tts` and `/api/tts-audio/*`.
  * `/api/reports/latest`.
* `web/ielts_server.py` is already marked deprecated, but still contains old
  fallback handlers.

## Requirements

* Add Django static frontend serving for local runtime:
  * `/`
  * `/index.html`
  * `/app.js`
  * `/styles.css`
* Add Django fallback contracts for:
  * `POST /api/p3/questions`
  * `POST /api/p3/follow-up`
  * `POST /api/tts`
  * `GET /api/tts-audio/{role}/{filename}`
  * `GET /api/reports/latest`
* Keep provider-heavy behavior deterministic and local-safe:
  * P3 returns fallback questions.
  * TTS returns browser fallback unless a file already exists for audio serving.
  * No real Azure/Codex/Volcengine integration.
* Keep `web/ielts_server.py` deprecated but do not delete it in this task.
* Add tests that prove Django covers the remaining contracts.
* Preserve frontend slashless billing calls:
  * `GET /api/billing/wallet`
  * `POST /api/billing/recharge`

## Acceptance Criteria

* [x] Django serves the frontend root and static JS/CSS.
* [x] Django has `/api/p3/questions` and `/api/p3/follow-up` fallback responses.
* [x] Django has `/api/tts` browser fallback response.
* [x] Django has `/api/tts-audio/*` route with deterministic 404 or file serving.
* [x] Django has `/api/reports/latest`.
* [x] Remaining frontend `/api/*` calls are covered by Django routes.
* [x] Tests pass and old server remains deprecated.

## Out of Scope

* Real provider integration.
* Deleting `web/ielts_server.py`.
* Production static asset pipeline.
* Billing changes.

## Technical Notes

* Static files live under `web/static`.
* TTS fallback should return `{"provider": "browser", "status": "fallback",
  "audio_url": null}`.
