# Journal - JMaa32 (Part 2)

> Continuation from `journal-1.md` (archived at ~2000 lines)
> Started: 2026-05-30

---



## Session 56: Retire legacy server and split production service boundaries

**Date**: 2026-05-30
**Task**: Retire legacy server and split production service boundaries
**Branch**: `main`

### Summary

Froze web/ielts_server.py as legacy reference, switched docs/scripts to Django-only runtime, added retirement validation, split writing validation/search helpers and speaking text helpers, and documented frontend/backend architecture boundaries.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `ebd0a8d` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 57: Split shared frontend UI helpers

**Date**: 2026-05-30
**Task**: Split shared frontend UI helpers
**Branch**: `main`

### Summary

Extracted shared frontend escaping and markdown helpers into shared-ui.js, served the asset through Django, and kept app.js using the shared compatibility surface.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `73a3f25` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 58: Split writing prompt services

**Date**: 2026-05-30
**Task**: Split writing prompt services
**Branch**: `main`

### Summary

Extracted writing prompt catalog, seed synchronization, random prompt selection, and agent prompt search into prompt_services.py while keeping apps.writing.services as the compatibility facade.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `acfa5c1` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 59: Split speaking corpus services

**Date**: 2026-05-30
**Task**: Split speaking corpus services
**Branch**: `main`

### Summary

Extracted speaking question bank, P1/P2 corpus, Takeaway, and translation helpers into corpus_services.py while preserving apps.speaking.services compatibility imports.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `87dfb55` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 60: Split speaking report history services

**Date**: 2026-05-30
**Task**: Split speaking report history services
**Branch**: `main`

### Summary

Extracted speaking report validity, history/detail/delete payloads, AI task summary payloads, and weak-item/replay-queue read services into backend_django/apps/speaking/report_services.py. Kept apps.speaking.services as the compatibility facade. Verified speaking tests, full Django tests, system checks, migrations dry-run, and legacy retirement validator.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 61: Split writing report services

**Date**: 2026-05-30
**Task**: Split writing report services
**Branch**: `main`

### Summary

Extracted writing summary, report list payloads, entry payloads, score payload shaping, and learner profile snapshots into backend_django/apps/writing/report_services.py. Kept apps.writing.services as the compatibility facade for existing views, tests, and worker callbacks. Verified writing tests, full Django tests, system checks, migrations dry-run, and legacy retirement validator.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 62: Split speaking scoring helpers

**Date**: 2026-05-30
**Task**: Split speaking scoring helpers
**Branch**: `main`

### Summary

Extracted pure speaking scoring calibration, heuristic fallback scoring, relevance caps, transcript counters, and turn habit/focus tagging into backend_django/apps/speaking/scoring_services.py. Kept apps.speaking.services as the compatibility facade. Verified speaking tests, full Django tests, system checks, migrations dry-run, and legacy retirement validator.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 63: Split frontend appearance controls

**Date**: 2026-05-30
**Task**: Split frontend appearance controls
**Branch**: `main`

### Summary

Extracted local font style and dark mode behavior from web/static/app.js into web/static/appearance.js, added Django static serving for /appearance.js, and verified JS syntax, Django check, asset smoke, diff check, and legacy-server retirement validation.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `19088d2` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 64: Split frontend API client

**Date**: 2026-05-30
**Task**: Split frontend API client
**Branch**: `main`

### Summary

Extracted frontend CSRF caching and JSON API request handling from web/static/app.js into web/static/api-client.js, served it through Django, and verified JS syntax, Django check, static asset smoke, diff check, and legacy-server retirement validation.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `355d26f` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 65: Split speaking TTS services

**Date**: 2026-05-30
**Task**: Split speaking TTS services
**Branch**: `main`

### Summary

Extracted low-level speaking TTS fallback, VolcEngine synthesis, cache URL lookup, and media path lookup from apps.speaking.services into apps.speaking.tts_services while preserving services.py public imports and examiner TTS orchestration. Verified speaking tests, full Django tests, check, migration dry-run, diff check, and legacy retirement validation.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `c6a81ae` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 66: Tighten legacy server retirement boundary

**Date**: 2026-05-30
**Task**: Tighten legacy server retirement boundary
**Branch**: `main`

### Summary

Documented the frozen legacy server archive boundary and strengthened scripts/validate_legacy_server_retirement.py to verify the retirement doc, startup guard, Django backend import isolation, Django URL surface, Windows launcher, and accidental legacy startup blocking.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `5543f1e` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 67: Split speaking candidate audio services

**Date**: 2026-05-30
**Task**: Split speaking candidate audio services
**Branch**: `main`

### Summary

Extracted candidate audio upload, media path lookup, and server-ASR handoff from apps.speaking.services into apps.speaking.audio_services while preserving services.py import compatibility. Verified speaking tests, full Django tests, check, migration dry-run, diff check, and legacy retirement validation.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `711586d` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 68: Split frontend view router

**Date**: 2026-05-30
**Task**: Split frontend view router
**Branch**: `main`

### Summary

Extracted URL parsing/building and route helper functions from web/static/app.js into web/static/view-router.js, added Django static serving for /view-router.js, and verified JS syntax, Django check, static asset smoke, diff check, and legacy-server retirement validation. Used partial staging to keep unrelated existing app/index/styles changes out of the commit.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `4676d36` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 69: Integrate legacy retirement validation into deliverables

**Date**: 2026-05-30
**Task**: Integrate legacy retirement validation into deliverables
**Branch**: `main`

### Summary

Connected the legacy server retirement validator to the software construction aggregate validation script, verified the standalone retirement checks and the full deliverables validation, archived the Trellis task, and left unrelated business WIP unstaged.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `867427b` | (see git log) |
| `5e0c748` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 70: Enable WASM audio preprocessing by default

**Date**: 2026-05-30
**Task**: Enable WASM audio preprocessing by default
**Branch**: `main`

### Summary

Verified audio_core WASM in a real browser, added Django /wasm static serving, confirmed fallback to mock-rms on WASM load failure, enabled wasm-audio-core by default, and archived the Trellis task while leaving unrelated WIP unstaged.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `9169c6c` | (see git log) |
| `075fb51` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 71: Add HTTP API provider for fast speaking follow-ups

**Date**: 2026-05-30
**Task**: Add HTTP API provider for fast speaking follow-ups
**Branch**: `main`

### Summary

Implemented an OpenAI-compatible HTTP provider for latency-sensitive P1/P3 speaking follow-ups. Follow-up generation now tries HTTP first, falls back to Codex CLI, then explicit local fallback metadata. Added focused tests, a benchmark diagnostic script, backend quality guidance, and task research/changes notes. Validation: manage.py check, targeted provider/follow-up tests, apps.ai tests, full Django test suite, makemigrations dry-run, and diagnostic script.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
