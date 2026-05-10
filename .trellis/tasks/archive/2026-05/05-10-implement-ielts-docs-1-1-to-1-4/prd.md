# Implement IELTS Docs 1.1-1.4

## Goal

Turn the existing IELTS 1.1-1.4 documents into working, tested product code. The user explicitly wants implementation, not another research pass. The work must be incremental and honest about current state: 1.1 is partially implemented, 1.3 is mostly not implemented, and 1.4 billing is currently documentation/research only.

## Current Reality

- The web runtime already has core IELTS mock practice, scored history, official-rubric score fields, pronunciation assessment status, and a `china_explanation` report block.
- The Chinese explanation and pronunciation-status work covers part of doc 1.1, but still needs audit and tests for user-facing wording and scoring provenance.
- The simulator plan is partly implemented in both C++ CLI and Python web paths, but the web product is the current user-facing target and should not be destabilized by a broad C++ rewrite.
- The adaptive weak-question system from 1.3 is not present as a real data model or replay scheduler. Existing `prompt_relevance()` and adaptive P3 follow-up are only supporting pieces.
- The Codex token billing and wallet deduction system from 1.4 is not implemented. There is no runtime wallet, ledger, reservation, settlement, price snapshot, or usage-capture path.

## Requirements

- Implement doc 1.1 as real scoring/report behavior:
  - Keep `ielts_score` as the single score source.
  - Keep China-facing explanation as guidance only, with natural Chinese copy.
  - Show scoring backend/provenance and pronunciation assessment status clearly.
  - Ensure overall band is recomputed from dimensions and rounded to nearest 0.5.

- Implement the web-relevant part of the simulator plan:
  - Preserve current P1/P2/P3/mock flows.
  - Keep real IELTS-like P1 intro questions, P2 cue-card timing, and P3 topic/follow-up behavior testable.
  - Do not replace the working web flow with the older C++ plan.

- Implement doc 1.3 adaptive weak-question training:
  - Persist turn-level training observations after scoring.
  - Store stable question identifiers, transcript, score dimensions, relevance, weak flags, weak reasons, and due/replay metadata.
  - Add a backend API to inspect weak items and replay queue.
  - Use conservative first-version heuristics instead of pretending to have a mature IRT/Bayesian model.
  - Surface weak-question labels and next due/replay information in the web UI.

- Implement doc 1.4 Codex token billing and balance deduction:
  - Add a standalone SQLite billing ledger under the configured reports directory, not inside attempt JSON.
  - Create a default local user with an initial 5 RMB grant stored in integer micro-RMB.
  - Add versioned price snapshots and integer fixed-point charge calculation.
  - Capture raw Codex JSONL usage events when Codex calls are enabled.
  - Settle each `call_id` idempotently; repeated settlement must not double-charge.
  - If authoritative usage is missing, do not guess a charge.
  - Expose wallet balance and recent ledger entries through JSON APIs and minimal UI.

## Acceptance Criteria

- [ ] Existing IELTS web tests pass.
- [ ] New tests prove 1.1 score/provenance/explanation behavior.
- [ ] New tests prove weak-question observations are persisted after scoring and can be listed by API.
- [ ] New tests prove replay candidate ranking prefers weak/due items without fully eliminating normal coverage.
- [ ] New tests prove initial wallet grant is exactly 5 RMB in integer units.
- [ ] New tests prove cached input tokens are charged separately from uncached input tokens.
- [ ] New tests prove `reasoning_output_tokens` is not double-counted.
- [ ] New tests prove settlement is idempotent for the same `call_id`.
- [ ] New tests prove missing usage creates no blind deduction.
- [ ] Frontend remains clickable and `node --check web/static/app.js` passes.
- [ ] Python compile/tests pass for backend changes.

## Technical Approach

Implement in small vertical slices:

1. Baseline repair and audit
   - Verify current `web/static/app.js` and `web/ielts_server.py` syntax.
   - Add tests around existing 1.1 behavior before extending it.

2. 1.1 scoring/report hardening
   - Tighten score provenance fields and Chinese report wording.
   - Keep pronunciation as `not_assessed` or provider-assessed; do not fake official pronunciation scoring.

3. 1.3 training observation model
   - Add a small JSON/SQLite-backed training store in `reports/training` or `reports/training.sqlite3`.
   - Persist observations from scored attempts.
   - Add weak item API and UI display.

4. 1.4 billing ledger
   - Add a dedicated billing module with SQLite schema, price snapshots, wallet grant, reserve/settle helpers, and usage normalization.
   - Integrate Codex call wrappers to record usage when available.
   - Add wallet API/UI.

5. Verification
   - Run backend tests, `node --check`, Python compile, and any focused C++ checks only if touched.

## Decision (ADR-lite)

Context: The docs span research, scoring UX, adaptive education logic, and financial ledger behavior. Trying to land everything as one rewrite would be risky and would repeat the earlier UI breakage.

Decision: Implement the web product path first, with strict tests for each slice. Keep C++ simulator plan behavior intact unless a test reveals a shared contract issue. For 1.3, ship a conservative heuristic model with persisted observations before claiming statistical adaptation. For 1.4, ship a real append-only ledger and idempotent settlement before claiming billing support.

Consequences: The first implementation will not be a full IRT/Bayesian training engine and will not use live official pricing unless configured. It will, however, create the real data contracts needed to evolve safely.

## Out of Scope

- Full production authentication; use a stable default local user for now.
- Claiming official IELTS examiner scoring or a China-specific score conversion.
- Building a full IRT/Bayesian model in the first pass.
- Charging without authoritative token usage.
- Rewriting the C++ CLI unless needed for shared tests or contracts.

## Technical Notes

- Main backend: `web/ielts_server.py`
- Main frontend: `web/static/app.js`, `web/static/index.html`, `web/static/styles.css`
- Test file: `tests/test_ielts_web_server.py`
- Existing docs:
  - `docs/IELTS_SIMULATOR_PLAN.md`
  - `docs/IELTS_CHINA_SCORING_STANDARD_1_1.md`
  - `docs/IELTS_ADAPTIVE_WEAK_QUESTION_TRAINING_1_3.md`
  - `docs/CODEX_TOKEN_BILLING_BALANCE_DEDUCTION_1_4.md`
- Relevant specs:
  - `.trellis/spec/backend/index.md`
  - `.trellis/spec/backend/quality-guidelines.md`
  - `.trellis/spec/frontend/index.md`
  - `.trellis/spec/frontend/quality-guidelines.md`
  - `.trellis/spec/guides/index.md`

