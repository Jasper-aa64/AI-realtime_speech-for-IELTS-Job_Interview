# Split Frontend App Modules Production Pass

## Goal

Continue the production refactor by extracting a safe, shared frontend utility
boundary from the large `web/static/app.js` file while preserving the current
static Django deployment and browser behavior.

## Requirements

- Keep the current SPA behavior and URLs unchanged.
- Do not introduce a bundler or framework.
- Extract reusable HTML escaping and markdown rendering helpers into a separate
  static script loaded before `app.js`.
- Keep global compatibility for existing `app.js` call sites.
- Validate JavaScript syntax and Django static serving compatibility.

## Acceptance Criteria

- [x] `web/static/shared-ui.js` contains shared escaping/markdown helpers.
- [x] `web/static/index.html` loads `shared-ui.js` before `app.js`.
- [x] `app.js` no longer owns the extracted helper implementations and consumes the shared boundary.
- [x] `node --check web/static/shared-ui.js` passes.
- [x] `node --check web/static/app.js` passes.
- [x] Django system check passes.
- [x] No user-facing behavior intentionally changes.

## Out of Scope

- Framework migration.
- Full `app.js` decomposition in one pass.
- Visual redesign.
- Backend behavior changes.
