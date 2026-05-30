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
