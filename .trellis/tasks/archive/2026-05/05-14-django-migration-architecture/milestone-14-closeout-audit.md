# Milestone 14 - Closeout Audit

## Goal

Finish the interrupted Milestone 12/13 batch by backfilling the missing task
notes, verifying that existing README/spec wording still matches the landed
Django changes, and rerunning the required backend checks without expanding
scope.

## Scope

Included:

* review the current partial Django/backend/doc changes relevant to provider
  usage metadata and the writing entry detail contract;
* add milestone notes for Milestones 12 and 13;
* record this close-out audit and the verification rerun.

Excluded:

* no new functional backend scope unless a concrete test/doc mismatch appears;
* no legacy `web/ielts_server.py` or `web/static/*` edits;
* no unrelated dirty-worktree cleanup or revert work.

## Files Changed

* `.trellis/tasks/05-14-django-migration-architecture/milestone-12-provider-usage-metadata.md`
* `.trellis/tasks/05-14-django-migration-architecture/milestone-13-writing-api-bridge-contract.md`
* `.trellis/tasks/05-14-django-migration-architecture/milestone-14-closeout-audit.md`

## Design Decisions

* Treat the already-landed Django code and tests as the source of truth. This
  close-out adds documentation for the interrupted milestones instead of
  reopening functional design.
* Keep README/spec edits out of scope unless the wording is actually wrong. The
  current partial README/spec updates already match the landed code paths, so
  the close-out stays doc-note-only.
* Record the verification rerun in a dedicated close-out note so Milestones 12
  and 13 can reference one honest final validation pass instead of repeating
  speculative historical results.

## Verification

The required commands were rerun after the milestone notes were added:

* `python3 -m py_compile backend_django/manage.py $(find backend_django/apps -maxdepth 4 -name '*.py' -print)`
  * Result: passed
* `.venv-django/bin/python backend_django/manage.py check`
  * Result: `System check identified no issues (0 silenced).`
* `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
  * Result: `No changes detected`
* `.venv-django/bin/python backend_django/manage.py test apps.ai apps.writing apps.billing -v 1`
  * Result: `Ran 65 tests in 7.797s ... OK`

## Known Gaps

* This close-out does not add a real provider client. Provider routing remains
  deterministic local scaffolding plus the new usage audit metadata surface.
* The writing bridge contract is frozen through tests/docs only; the legacy
  frontend still needs a later migration milestone to consume it.
* The repo still contains many unrelated uncommitted changes outside this task
  scope and they were intentionally left untouched.

## Rollback

Rollback for this close-out is documentation-only: revert the three milestone
notes if the team wants to rewrite the milestone history. The underlying
functional rollback points remain the same ones documented in Milestones 12 and
13.

## Next Recommendation

Choose the next milestone based on product priority:

* if billing/provider fidelity matters first, add the first real provider-backed
  writing adapter behind the existing provider config boundary;
* if client migration matters first, bridge the current writing UI to the
  durable Django entry detail contract without changing the legacy server in the
  same batch.
