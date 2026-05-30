# Integrate legacy retirement validation into deliverables

## Goal

Close the legacy server retirement verification loop by making the software construction aggregate validation script run the existing legacy retirement validator.

## Scope

- Update `scripts/run_software_construction_deliverables_validation.sh` to invoke `scripts/validate_legacy_server_retirement.py`.
- Keep `docs/SPEC-legacy-server-retirement-validation.md` and `docs/SPEC-speaking-services-split.md` as the design/verification handoff documents for this refactor line.
- Do not change product code, frontend code, Django app code, local database files, or unrelated WIP.

## Out of Scope

- No changes to `web/ielts_server.py`.
- No changes to `backend_django/`.
- No changes to `web/static/`.
- No changes to existing business-line dirty files.
- No push.

## Acceptance Criteria

- [x] `python3 scripts/validate_legacy_server_retirement.py` exits 0.
- [x] `bash scripts/run_software_construction_deliverables_validation.sh` exits 0 and includes the legacy retirement validation step.
- [x] Only the aggregate validation script, the two SPEC docs, and this task's Trellis files are included in the work commit.
- [x] Existing unrelated dirty files remain unstaged and untouched.
