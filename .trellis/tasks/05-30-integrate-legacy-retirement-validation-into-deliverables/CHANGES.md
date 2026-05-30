# Changes

## What Changed

- Added the existing legacy server retirement validator to `scripts/run_software_construction_deliverables_validation.sh`.
- Updated `docs/SPEC-legacy-server-retirement-validation.md` to reflect the current Python validator instead of the older shell-script plan.
- Kept `docs/SPEC-speaking-services-split.md` available as the speaking service split handoff/spec document for this refactor line.

## Verification

- `python3 scripts/validate_legacy_server_retirement.py`
  - PASS `ensure_readme_is_django_only`
  - PASS `ensure_retirement_doc_exists`
  - PASS `ensure_legacy_file_is_frozen`
  - PASS `ensure_django_backend_has_no_legacy_imports`
  - PASS `ensure_windows_launcher_is_django_only`
  - PASS `ensure_django_url_surface_exists`
  - PASS `ensure_legacy_startup_is_blocked`
- `bash scripts/run_software_construction_deliverables_validation.sh`
  - Passed Experiment 2 design validation.
  - Passed Experiment 3 TDD validation.
  - Passed Experiment 4 refactor validation.
  - Passed Experiment 5 open-source reuse and WASM validation.
  - Passed legacy server retirement validation.

## Boundaries

- No production code changed.
- No frontend files changed.
- No Django app files changed.
- Existing unrelated dirty files were not staged.
