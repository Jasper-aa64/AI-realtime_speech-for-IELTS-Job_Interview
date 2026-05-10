# Codex token billing balance deduction research doc 1.4

## Goal

Produce a standalone implementation plan for deducting per-user RMB wallet balance from Codex usage, based on actual token usage returned by Codex / OpenAI usage objects. Every user starts with 5 RMB, billing must be auditable and precise, and the plan must not rely on toy heuristics.

## What I already know

* The local Codex CLI returns `turn.completed.usage` in JSON mode with `input_tokens`, `cached_input_tokens`, `output_tokens`, and `reasoning_output_tokens`.
* The local Codex CLI output I observed does **not** include a direct RMB cost field.
* OpenAI Responses usage docs say `input_tokens` includes cached tokens; cached tokens must be separated for billing.
* OpenAI reasoning docs say reasoning tokens are billed as output tokens and appear in the usage object as part of output-token breakdowns.
* The current repo uses Codex by shelling out through Python and currently discards usage accounting entirely.
* The project presently has no wallet, no ledger, no user identity layer for billing, and no per-call idempotency key.

## Assumptions (temporary)

* The app-level wallet is denominated in RMB and is independent of any provider-native credit system.
* The first implementation should be provider-agnostic but must support Codex/Responses usage as the canonical input for accounting.
* "Accurate" means: no float math, immutable usage capture, versioned price table, and idempotent settlement.

## Open Questions

* None blocking. The implementation plan can proceed with the above assumptions.

## Requirements (evolving)

* Define how to capture actual token usage from Codex calls.
* Define a balance ledger with an initial 5 RMB grant per user.
* Define how to convert usage into RMB using a versioned pricing snapshot.
* Define reservation / settlement / reconciliation so concurrent requests do not overspend.
* Define what to do when a call fails, returns no usage, or exceeds estimate.
* Tie the plan back to the current repo files that need to change.

## Acceptance Criteria (evolving)

* [ ] A standalone markdown document exists under `docs/` with version `1.4` in the title.
* [ ] The document explicitly states that Codex returns token usage but not guaranteed RMB cost.
* [ ] The document defines an exact RMB ledger model with integer minor units and idempotent settlements.
* [ ] The document includes source links to official OpenAI docs and references local Codex usage evidence.
* [ ] The document includes a realistic rollout and reconciliation plan for the existing repo.

## Definition of Done

* Research notes are captured in the task directory.
* Final markdown document is written and reviewed for billing correctness.
* Source links are present and clearly attributed.

## Out of Scope

* No code changes in this task.
* No attempt to invent a provider billing rate without a versioned pricing snapshot.
* No user-facing payment integration beyond wallet deduction.

## Technical Notes

* Local Codex usage observation: `codex exec --json` returns a `turn.completed.usage` object with token counts but no cost field.
* Relevant repo files:
  * `web/ielts_server.py`
  * `web/static/app.js`
  * `reports/attempts/`
  * `config/default_config.json`
  * `src/ielts/scorer.cpp` for the C++ Codex-shell-out path
* Official references:
  * OpenAI Responses usage object: `https://platform.openai.com/docs/api-reference/responses/retrieve`
  * OpenAI Responses usage aggregation: `https://platform.openai.com/docs/api-reference/usage?api-mode=responses&lang=curl`
  * OpenAI reasoning guide: `https://platform.openai.com/docs/guides/reasoning?api-mode=responses`
  * Codex rate card: `https://help.openai.com/en/articles/20001106-codex-rate-card`
