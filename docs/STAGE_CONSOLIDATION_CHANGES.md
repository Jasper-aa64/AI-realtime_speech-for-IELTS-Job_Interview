# Stage Consolidation Changes

## Scope

This consolidation pass did not change product behavior. It closed the documentation and validation loop for the current refactor stage, separated refactor-owned artifacts from business WIP, and recorded the remaining architecture debt.

## Committed in This Pass

- `docs/SPEC-stage-consolidation.md`
  - Stage consolidation acceptance spec.
  - Defines the dirty-worktree classification rules and the remaining refactor completion report requirement.
- `软件构造/重构完成度报告.md`
  - Current architecture/refactor status report.
  - Documents completed refactor lines, baseline line counts, remaining debt, and next recommended priorities.
- `docs/STAGE_CONSOLIDATION_CHANGES.md`
  - This change summary.

## Deliberately Not Submitted

The following files remain business WIP or local state and were not staged:

- `web/static/app.js`
- `web/static/index.html`
- `web/static/styles.css`
- `backend_django/apps/speaking/services.py`
- `backend_django/apps/speaking/views.py`
- `backend_django/apps/speaking/tests.py`
- `backend_django/apps/speaking/corpus_services.py`
- `backend_django/apps/writing/tests.py`
- `data/ielts/part2/2026_may_august_topics.json`
- `.trellis/tasks/05-30-add-current-speaking-season-bank-to-account-profile/`
- `scripts/ielts_agent_cli.py`
- `scripts/evaluate_writing_prompt_search.py`
- `backend_django/db.sqlite3`

`backend_django/apps/speaking/corpus_services.py` was classified as business WIP, not pure refactor cleanup, because its diff adds current-season question-bank scope behavior, stable corpus IDs, and P1/P2 corpus library changes.

## Validation

- `bash scripts/run_software_construction_deliverables_validation.sh`
- `cd backend_django && python3 manage.py check`
- `cd backend_django && python3 manage.py test`

All validation passed in this workspace before committing this consolidation pass.
