# Split Frontend View Routing Module for Production Refactor

## Goal

Continue reducing `web/static/app.js` by extracting pure view-route helper logic into a dedicated browser module, without changing SPA navigation behavior or existing dirty UI edits.

## Scope

In scope:
- Add `web/static/view-router.js`.
- Move route URL parsing/building/persist helper logic out of `app.js` where practical.
- Load the new module before `app.js`.
- Serve `/view-router.js` through the Django frontend asset allowlist.
- Preserve existing `switchView()` behavior and auth gate behavior in `app.js`.

Out of scope:
- Page rendering behavior.
- Auth flow changes.
- Sidebar/layout CSS.
- Existing uncommitted account/weak-training edits.

## Acceptance Criteria

- Existing `?view=...` URLs continue to load the same views.
- Route helpers are available through `window.IELTSViewRouter`.
- `node --check web/static/view-router.js` passes.
- `node --check web/static/app.js` passes.
- Django check and static asset smoke pass.
- Only route-split files/hunks are committed; unrelated dirty UI files remain untouched.
