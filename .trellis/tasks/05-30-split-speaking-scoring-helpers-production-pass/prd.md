# Split Speaking Scoring Helpers Production Pass

## Goal

Continue the production refactor by reducing `backend_django/apps/speaking/services.py` without changing scoring behavior. This pass extracts pure speaking scoring calibration and turn habit helper functions into a cohesive module while keeping `apps.speaking.services` as the compatibility facade for existing callers.

## Scope

- Add a focused speaking scoring/helper module.
- Move pure helper functions related to band clamping, realistic calibration, relevance caps, heuristic fallback scoring, part-specific scoring guidance, transcript word counts, repeated phrase detection, turn habit tags, and primary focus inference.
- Preserve public imports from `apps.speaking.services`.
- Do not change Codex prompts, provider behavior, report generation, TTS, ASR, attempt runtime state, or database schema.

## Acceptance Criteria

- `services.py` is smaller and no longer owns pure scoring calibration helpers.
- New module does not import from `services.py`.
- Existing speaking tests pass.
- Full Django tests pass.
- Legacy retirement validator still passes.
- No unrelated dirty files are staged.

## Validation Plan

- `python3 -m py_compile backend_django/apps/speaking/services.py backend_django/apps/speaking/scoring_services.py`
- `cd backend_django && python3 manage.py test apps.speaking.tests -v 1`
- `cd backend_django && python3 manage.py test -v 1`
- `cd backend_django && python3 manage.py check`
- `cd backend_django && python3 manage.py makemigrations --check --dry-run`
- `python3 scripts/validate_legacy_server_retirement.py`
- `git diff --check`
