# Prevent Initial Home Flash for Direct Corpus Views

## Goal

Remove the visible first-load flash where a direct `?view=p1Corpus` / `?view=p2Corpus` / `?view=takeawayBook` page briefly renders the default home view before JavaScript switches to the requested view.

## Root Cause

The static HTML defaults to the home page being visible. `init()` reads the URL and calls `switchView(savedView)` only after JavaScript loads and account state initializes, so users can see the home view before the target corpus page appears.

## Requirements

- Hide the main workspace during boot until the initial `switchView()` has applied.
- Preserve normal home rendering after initialization.
- Do not change API behavior or corpus loading behavior.
- Keep navigation and top bar stable.

## Acceptance Criteria

- [x] Direct `?view=p1Corpus` no longer visibly flashes home content first.
- [x] Direct `?view=p2Corpus` no longer visibly flashes home content first.
- [x] Direct `?view=takeawayBook` no longer visibly flashes home content first.
- [x] Normal `/` still shows the home page after initialization.
- [x] JS syntax check passes.

## Technical Notes

- Main files: `web/static/index.html`, `web/static/app.js`, `web/static/styles.css`.
- Add a boot class to `body`, hide `.workspace` during boot, and remove it after initial view selection.
