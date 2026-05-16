# Fix speaking audio upload csrf token

## Goal

Restore the speaking practice recording flow by sending the Django CSRF token with the browser audio upload request.

## Problem

The speaking start endpoint works, but after recording an answer the frontend uploads audio with a raw `fetch()` call. Django rejects that multipart/body upload with:

- `403 CSRF token missing`
- `Forbidden: /api/attempts/{attempt_id}/turns/{turn_id}/audio`

The shared `api()` helper already injects `X-CSRFToken` for JSON requests, but the raw audio upload bypasses that helper.

## Scope

- Update `web/static/app.js` only.
- Keep backend CSRF protection enabled.
- Do not set an incorrect multipart boundary or weaken upload validation.
- Do not change speaking flow behavior beyond making the upload request authenticated with CSRF.

## Acceptance Criteria

- [x] Audio upload request sends `X-CSRFToken` when available.
- [x] Audio upload still sends the recorded blob body and keeps the existing content type behavior.
- [x] The existing complete-turn request remains handled through `api()`.
- [x] `node --check web/static/app.js` passes.
- [x] Django speaking tests pass.
- [x] Full Django tests pass.
- [x] Django system check passes.
- [x] Migration dry-run reports no changes.
