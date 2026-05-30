# Split Frontend Appearance Controls for Production Refactor

## Goal

Reduce `web/static/app.js` size and improve frontend architecture clarity by extracting local appearance controls into a dedicated browser module, without changing product behavior.

## Scope

In scope:
- Extract font style and dark mode helpers from `web/static/app.js`.
- Add a new `web/static/appearance.js` loaded before `app.js`.
- Keep the existing localStorage keys, DOM behavior, transition delay, and state updates unchanged.
- Update Django's explicit frontend asset allowlist so `appearance.js` is served by the Django runtime.
- Verify JavaScript syntax and Django static asset configuration.

Out of scope:
- Page routing.
- Practice/report/business state.
- CSS redesign.
- Any changes to existing user workflows.

## Acceptance Criteria

- `app.js` no longer defines the appearance helper bodies directly.
- Existing calls to `applyFontStyle`, `applyDarkMode`, `loadFontStyle`, and `loadDarkMode` still work from `app.js`.
- `/appearance.js` is loadable through Django's frontend asset surface.
- `node --check web/static/appearance.js` passes.
- `node --check web/static/app.js` passes.
- `python backend_django/manage.py check` passes.
- Legacy runtime validation still passes.

