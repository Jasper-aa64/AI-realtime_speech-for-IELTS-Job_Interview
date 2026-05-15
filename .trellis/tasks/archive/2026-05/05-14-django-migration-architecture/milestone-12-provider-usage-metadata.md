# Milestone 12 - Provider Usage Metadata

## Goal

Persist durable provider/model audit context on settled billing usage records so
successful billable AI tasks can be traced back to the originating Django
`AITask` and writing identifiers without changing the existing fallback-first
worker flow.

## Scope

Included:

* add a JSON metadata field to `billing.CodexUsageEvent`;
* extend billing usage capture/settlement helpers to accept optional
  `provider`, `model`, and `metadata` inputs while keeping older callers
  working;
* stamp usage audit metadata from successful billable AI task settlement;
* cover the new persistence contract with billing and AI worker tests;
* document the audit contract in backend README/spec notes.

Excluded:

* no new real provider SDK integration;
* no legacy `web/ielts_server.py` or `web/static/*` edits;
* no frontend bridge implementation work;
* no schema changes outside the billing usage event metadata field.

## Files Changed

* `backend_django/apps/billing/models.py`
* `backend_django/apps/billing/migrations/0003_codexusageevent_metadata.py`
* `backend_django/apps/billing/services.py`
* `backend_django/apps/billing/tests.py`
* `backend_django/apps/ai/orchestration.py`
* `backend_django/apps/ai/tests.py`
* `backend_django/README.md`
* `.trellis/spec/backend/database-guidelines.md`
* `.trellis/spec/backend/quality-guidelines.md`

## Design Decisions

* Usage audit context lives on `CodexUsageEvent.metadata`, not only in wallet
  ledger metadata or raw usage blobs. That keeps the settlement record itself
  queryable and durable.
* `capture_usage(...)` and `settle_usage(...)` now accept optional
  `provider`, `model`, `raw_jsonl_path`, and `metadata` parameters, but still
  default to the historical `codex` / `codex-cli` values for older callers.
* Existing `call_id` idempotency remains the source of truth. Repeated capture
  of the same usage event merges metadata and refreshes provider/model fields
  instead of creating duplicates.
* `apps.ai.orchestration.usage_audit_metadata(...)` derives audit metadata from
  durable task fields plus `request_payload` identifiers. The current contract
  records:
  * `task_id`
  * `task_type`
  * effective `provider`
  * effective `model`
  * `prompt_version`
  * `related_type`
  * `related_id`
  * `entry_id` and `prompt_id` when present in the writing task request
* Audit metadata is written only on successful billable settlement. Fallback,
  cancellation, and missing-authoritative-usage paths still avoid creating a
  settled usage event.

## Verification

Close-out rerun passed on 2026-05-15 and is recorded in
`milestone-14-closeout-audit.md`:

* `python3 -m py_compile backend_django/manage.py $(find backend_django/apps -maxdepth 4 -name '*.py' -print)` -> passed
* `.venv-django/bin/python backend_django/manage.py check` -> `System check identified no issues (0 silenced).`
* `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run` -> `No changes detected`
* `.venv-django/bin/python backend_django/manage.py test apps.ai apps.writing apps.billing -v 1` -> `Ran 65 tests ... OK`

Relevant coverage in this milestone:

* `backend_django/apps/billing/tests.py`
  * `test_settle_usage_can_store_optional_audit_metadata`
* `backend_django/apps/ai/tests.py`
  * worker success path asserts settled `CodexUsageEvent.provider`,
    `CodexUsageEvent.model`, and the expected metadata payload

## Known Gaps

* `metadata` is intentionally flexible JSON. There is no schema validator yet
  beyond the tested key set used by the current writing flow.
* Only successful billable settlement stamps provider usage metadata today.
  Pending-reconciliation usage still returns without a durable event.
* The current audit helper only promotes `entry_id` and `prompt_id` from the
  request payload. Future task types may need additional identifiers.

## Rollback

Rollback requires:

* reverting `billing` migration `0003_codexusageevent_metadata`;
* removing the metadata field and the new optional settle/capture arguments;
* restoring the previous orchestration settlement call sites;
* reverting the README/spec/test updates that describe or assert the contract.

## Next Recommendation

Use this durable usage audit trail as the billing side of the first real
provider-backed adapter or any later reconciliation/admin tooling, but keep the
AI task contract as the source of truth for routing decisions.
