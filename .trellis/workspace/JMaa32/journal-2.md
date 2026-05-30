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
