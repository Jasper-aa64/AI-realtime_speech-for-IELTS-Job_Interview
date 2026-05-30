# Production Refactor Retire Legacy Server

## Goal

Complete the product architecture refactor so the IELTS web product has one clear production runtime: Django serves the app, APIs, and static frontend; the old `web/ielts_server.py` is frozen as a reference artifact and cannot accidentally be used as production. In the same task, start the main architecture cleanup of the largest production modules so the system is still usable but no longer organized around monolithic files.

This is not a UI redesign and not a feature rewrite. Existing mature browser flows are the baseline. The work is retirement, boundary cleanup, module extraction, documentation, and verification.

## Highest Principle

Keep the current browser product usable. Do not replace working practice/report/writing/corpus flows with a new architecture. Refactor incrementally behind the same URLs and UI behavior.

## What I Already Know

- Current production runtime is intended to be `backend_django/` plus `web/static/`.
- `web/ielts_server.py` is already marked deprecated, but it is still executable and large enough to be mistaken for runtime.
- `README.md` still contains old instructions that start `python3 web/ielts_server.py`.
- `scripts/windows/start-ielts-stack.ps1` still starts both Django and the old web server and tunnels to the old web port.
- `backend_django/config/urls.py` already exposes the SPA entrypoints and the main `/api/*` surface.
- Large product modules still need systematic decomposition:
  - `backend_django/apps/speaking/services.py` (~232 KB)
  - `backend_django/apps/writing/services.py` (~83 KB)
  - `web/static/app.js` (~363 KB)
  - `web/static/styles.css` (~327 KB)
- There are pre-existing dirty files in the workspace. This task must avoid mixing unrelated changes and must not stage `backend_django/db.sqlite3` unless explicitly requested.

## Requirements

### A. Legacy Server Retirement

- Freeze `web/ielts_server.py` as a reference-only artifact.
- Prevent accidental production startup of the old server unless an explicit legacy override is set.
- Add clear documentation for the retirement boundary and rollback/reference process.
- Update runtime docs and scripts so normal local/public startup uses Django only.
- Mark old-server tests as legacy/frozen or move them out of the default production validation path.

### B. Product Architecture Refactor

- Create explicit service submodules around current monolith hot spots without changing public API contracts.
- Split by existing domain responsibilities, not by arbitrary line count.
- Maintain compatibility imports where needed to keep callers stable during the first refactor pass.
- Prioritize extraction targets that improve clarity and reduce future risk:
  - Speaking report generation / scoring / feedback helpers.
  - Speaking runtime attempt/turn orchestration.
  - Writing prompt search/report helpers already being split.
  - Frontend writing/report/corpus modules where they can be extracted safely without changing UI behavior.
- Add module-level documentation explaining what stays in the orchestration file and what moved.

### C. Verification

- Django remains the only production runtime in docs/scripts.
- Django URL coverage is verified for frontend static entrypoints and major API groups.
- Legacy server cannot start accidentally.
- Existing Django tests for touched modules pass.
- Frontend syntax remains valid.
- Add a retirement validation script that can be rerun later.

## Acceptance Criteria

- [x] `web/ielts_server.py` is frozen and direct startup exits with a clear retirement message unless explicitly overridden.
- [x] `README.md` documents Django-only runtime and no longer instructs users to run the old server.
- [x] Windows start script no longer launches `web/ielts_server.py` and tunnels to Django.
- [x] A legacy retirement document exists and explains archived/reference status, fallback policy, and rollback procedure.
- [x] Default validation no longer treats old server behavior as production behavior.
- [x] At least one high-value backend monolith extraction is completed with compatibility preserved and tests green.
- [x] At least one high-value frontend production module boundary is established or documented with a safe compatibility path.
- [x] `scripts/validate_legacy_server_retirement.py` or equivalent verifies the retirement invariants.
- [x] Targeted Django tests pass for affected apps.
- [x] `node --check web/static/app.js` passes.
- [x] No unrelated pre-existing dirty files are staged or modified by this task.

## Out Of Scope

- Deleting the old server file entirely in this pass.
- Replacing existing user-facing flows with a new frontend framework.
- Large-scale visual redesign.
- Real-time C++/WASM audio pipeline implementation.
- Changing AI provider behavior or prompt strategy unless required by extraction tests.
- Committing local database state unless explicitly requested.

## Technical Notes

- Primary runtime routes live in `backend_django/config/urls.py`.
- Old server tests live in `tests/test_ielts_web_server.py` and should be treated as frozen legacy coverage.
- Current Windows stack scripts are under `scripts/windows/`.
- Existing Trellis specs to follow:
  - `.trellis/spec/backend/index.md`
  - `.trellis/spec/frontend/index.md`
  - `.trellis/spec/guides/index.md`

## Definition Of Done

- The app can be started via Django only.
- The old server is impossible to start accidentally.
- The architecture has a clear production/runtime boundary and initial monolith split.
- The repo contains repeatable validation for the retirement.
- Worktree changes are scoped and reviewable.
