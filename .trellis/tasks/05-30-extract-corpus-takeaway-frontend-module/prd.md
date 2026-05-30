# Extract Corpus Takeaway Frontend Module

## Goal

Reduce `web/static/app.js` size and risk by moving corpus and Takeaway UI orchestration into a dedicated frontend module while preserving current behavior.

## Context

`app.js` is still large. The next safe extraction target is corpus/Takeaway because it is sizeable but outside the critical speaking recording runtime. This must not touch examiner playback, recording, WASM preprocessing, follow-up generation, or report scoring.

There is also a small uncommitted P1 corpus matching fix in the workspace. That fix must be handled separately before or alongside this task, without mixing it into the module extraction commit.

## Requirements

1. Clear or isolate the existing P1 corpus matching fix first.
   - Prefer a separate commit if it is valid and tests pass.
   - Do not mix it with the module extraction commit.
2. Add a dedicated frontend module, e.g. `web/static/corpus-takeaway.js`.
3. Move corpus/Takeaway rendering and editor orchestration out of `app.js` where practical.
4. Keep `app.js` as a facade/wiring layer for shared global state and existing event bindings.
5. Preserve existing behavior:
   - P1/P2 corpus library pages still render and edit normally.
   - Takeaway cards still show English/Chinese and hide English in hide mode.
   - selection/translation/takeaway popup behavior stays unchanged unless explicitly out of scope.
6. Do not touch speaking runtime, examiner playback, recording, WASM preprocessing, report scoring, or HTTP provider paths.
7. Add Django static route and index script tag for the new module, with cache-busting version bump.
8. Stop after this extraction and report the new `app.js` line count.

## Acceptance Criteria

- [ ] Existing P1 corpus matching fix is separately committed or explicitly left out of the extraction commit.
- [ ] New `web/static/corpus-takeaway.js` exists and syntax-checks.
- [ ] `app.js` no longer owns the moved corpus/Takeaway rendering logic except facade/wiring.
- [ ] `index.html` loads the new module before `app.js`.
- [ ] Django serves the new module with JavaScript content type.
- [ ] No product behavior/UI changes are intended.
- [ ] `node --check web/static/app.js` passes.
- [ ] `node --check web/static/corpus-takeaway.js` passes.
- [ ] `.venv-django/bin/python backend_django/manage.py check` passes.
- [ ] Smoke verifies page loads and module route returns 200 if practical.
- [ ] Final report includes `app.js` line count before/after this extraction.

## Out of Scope

- Speaking runtime extraction.
- Examiner audio playback fixes.
- Rewriting corpus APIs.
- Changing Takeaway card design.
- Changing translation provider behavior.
