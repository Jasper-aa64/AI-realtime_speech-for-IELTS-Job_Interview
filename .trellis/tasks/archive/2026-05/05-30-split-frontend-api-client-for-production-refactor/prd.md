# Split Frontend API Client for Production Refactor

## Goal

Reduce `web/static/app.js` size and clarify the Django-only frontend network boundary by extracting CSRF handling and JSON API request parsing into a dedicated browser module.

## Scope

In scope:
- Add `web/static/api-client.js`.
- Move `ensureCsrfToken()` and `api()` behavior out of `app.js`.
- Preserve cached CSRF behavior, JSON parsing, structured error shape, request signals, and same-origin credentials.
- Provide explicit helpers for cached CSRF access and CSRF reset so upload and keepalive flows remain unchanged.
- Load the new module before `app.js`.
- Serve `/api-client.js` through Django's frontend asset allowlist.

Out of scope:
- API endpoint behavior.
- Authentication UI.
- Upload flow semantics.
- Business state, routes, and reports.

## Acceptance Criteria

- `app.js` no longer owns the JSON API client implementation.
- Existing calls to `api()` and `ensureCsrfToken()` continue to work.
- Login/register/logout reset the cached CSRF token through the API client.
- Keepalive/autosave can still read the cached token synchronously.
- `/api-client.js` returns 200 from the Django static asset surface.
- `node --check web/static/api-client.js` and `node --check web/static/app.js` pass.
- `python backend_django/manage.py check` passes.
- Legacy server retirement validation still passes.

