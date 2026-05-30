# Document Legacy Server Retirement Boundary

## Goal

Make the retired `web/ielts_server.py` boundary auditable: it stays in the repository as a frozen reference artifact, while production startup and Django backend code remain free of legacy runtime dependencies.

## Scope

In scope:
- Strengthen `scripts/validate_legacy_server_retirement.py`.
- Ensure the retirement document explains the archive/frozen boundary.
- Ensure README points to the retirement validation.

Out of scope:
- Deleting `web/ielts_server.py`.
- Editing old server business logic.
- Refactoring Django features.

## Acceptance Criteria

- Validation confirms `docs/LEGACY_SERVER_RETIREMENT.md` exists and describes frozen/reference-only status.
- Validation confirms `web/ielts_server.py` has the default startup guard and allow env marker.
- Validation confirms `backend_django/` does not import or execute `web/ielts_server.py`.
- Existing validation checks still pass.
- No production feature behavior changes.

