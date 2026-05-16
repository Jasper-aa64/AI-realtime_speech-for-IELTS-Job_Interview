# Add feature-flagged Django speaking runtime cutover

## Goal

Let the old `web/ielts_server.py` proxy the already-migrated speaking runtime
endpoints to Django when a logged-in browser session is present, while keeping
the old server fallback behavior available if the flag is disabled or Django is
unavailable.

## What I Already Know

* Django now owns the fallback runtime chain:
  * `POST /api/attempts/start`
  * `POST /api/attempts/{attempt_id}/turns/{turn_id}/audio`
  * `POST /api/attempts/{attempt_id}/turns/{turn_id}/complete`
  * `POST /api/attempts/{attempt_id}/score`
  * `POST /api/attempts/{attempt_id}/abort`
  * `GET /api/audio/{attempt_id}/{turn_id}/candidate`
* The old server still serves static files and fallback runtime handlers.
* Existing proxy support handles JSON Django requests, but raw browser audio
  uploads must be proxied without parsing JSON.
* Existing proxy behavior is gated by cookies for writing/AI task paths.

## Requirements

* Add a feature flag for speaking runtime proxying.
* Proxy only migrated speaking runtime paths:
  * `/api/attempts/start`
  * `/api/attempts/{id}/turns/{turn_id}/audio`
  * `/api/attempts/{id}/turns/{turn_id}/complete`
  * `/api/attempts/{id}/score`
  * `/api/attempts/{id}/abort`
  * `/api/audio/{id}/{turn_id}/candidate`
* Require a `sessionid` cookie before proxying these paths.
* Preserve fallback to old server if Django is unavailable.
* Support raw Blob audio proxying with the original content type and body.
* Do not proxy or migrate provider-heavy paths:
  * `/api/tts`
  * `/api/p3/questions`
  * `/api/p3/follow-up`
  * regenerate endpoints
* Do not edit frontend or delete/freeze the old server in this task.

## Acceptance Criteria

* [x] Speaking runtime proxy flag exists and defaults conservatively.
* [x] With flag enabled and session cookie, JSON runtime POSTs proxy to Django.
* [x] With flag enabled and session cookie, raw audio upload proxies to Django.
* [x] With no session cookie, runtime requests stay on old server.
* [x] If Django is unavailable, runtime requests fall back to old server.
* [x] Provider-heavy paths remain on the old server.
* [x] Tests cover proxy routing, raw body forwarding, and fallback behavior.
* [x] Full validation passes.

## Definition of Done

* Old server proxy logic and tests are updated.
* PRD and milestone note document scope, changed files, validation, rollback,
  and remaining old-server dependencies.
* `tests/test_ielts_web_server.py`, Django tests, Django check, migration
  dry-run, and `node --check web/static/app.js` pass.
* Business commit, archive commit, and journal commit are created.

## Out of Scope

* Frontend changes.
* Direct Django static serving.
* TTS/P3/regenerate migration.
* Real provider integration.
* Billing changes.
* Deleting `web/ielts_server.py`.

## Technical Notes

* Candidate file: `web/ielts_server.py`.
* Test file: `tests/test_ielts_web_server.py`.
* Use `IELTS_DJANGO_PROXY_SPEAKING_RUNTIME`; default should keep legacy behavior
  unless explicitly enabled.
