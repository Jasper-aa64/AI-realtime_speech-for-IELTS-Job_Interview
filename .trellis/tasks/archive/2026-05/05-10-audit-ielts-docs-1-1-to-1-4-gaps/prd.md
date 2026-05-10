# Audit IELTS docs 1.1-1.4 remaining implementation gaps

## Goal

Verify whether any promised behavior from docs 1.1-1.4 is still missing after the prior implementation, and if so, land the smallest safe slice that closes the gap. The main suspected gap is in 1.4: reserve/release/reconciliation support exists in the doc but not yet as a product workflow.

## What I already know

* 1.1 scoring guidance and Chinese explanation are implemented and tested.
* 1.3 weak-question persistence, weak-items API, and replay queue are implemented and tested.
* 1.4 wallet/grant/settle-usage exists and is tested, including usage capture from `codex exec --json`.
* The 1.4 research doc also describes reservation, release, and reconciliation states, but the current code only exposes wallet and settle usage APIs.
* The repo already contains `wallet_reservations` in the billing SQLite schema.

## Assumptions (temporary)

* The smallest missing slice is a reserve / release / reconciliation API path, not a full rate-card rework.
* The existing wallet can stay integer micro-RMB.
* The UI only needs a minimal surface for any new billing workflow, not a redesign.

## Open Questions

* None blocking for the initial slice.

## Requirements (evolving)

* Keep 1.1 and 1.3 behavior intact.
* Add explicit reserve/release/reconciliation support for the local billing ledger if still missing.
* Preserve idempotency for repeat reserve/settle/release calls.
* Reuse the existing SQLite wallet schema where possible.

## Acceptance Criteria (evolving)

* [ ] Reserve/release/reconciliation paths exist and are covered by tests.
* [ ] Existing wallet and settle-usage tests still pass.
* [ ] No blind deduction occurs when usage is missing.
* [ ] If a reservation is created and later released, the wallet balance returns correctly.

## Definition of Done

* Tests added/updated.
* Lint / typecheck / unit tests green.
* Docs/spec updated if contract changes.

## Out of Scope

* Full production auth.
* Full external provider reconciliation pipeline.
* Reworking 1.1 or 1.3 behavior.

## Technical Notes

* Backend: `web/ielts_server.py`
* Tests: `tests/test_ielts_web_server.py`
* Billing schema already includes `wallet_reservations`.
* Related docs: `docs/CODEX_TOKEN_BILLING_BALANCE_DEDUCTION_1_4.md`
