# Fix Speaking AI Feedback Quality and Fallback Policy

## Goal

Make Speaking AI feedback behave like real AI coaching instead of rule-heavy templates. The system should use Codex for Band 7 rewrites, coaching, and generated follow-ups whenever possible, keep only minimal safety/format validation, and make fallback states transparent instead of presenting hardcoded answers as AI output.

## What I Already Know

- The previous fixes hardened `run_codex()` and scoring validation, but the product still over-constrains coaching and falls back to hardcoded answers.
- P1 work/study fallback misclassified `software engineering student + internship` as `software engineer`.
- P1 identity follow-up is currently metadata-marked as `backend=fallback` / `generation_status=skipped_sync_ai`, so it is not AI-generated.
- The user wants AI to decide coaching structure naturally, with only one preserved format contract: keep a final `语法错误纠正：` section.
- The user explicitly rejects cumbersome vocabulary/rule detection and if/else driven feedback.

## Requirements

- AI coaching prompt must stop teaching the model a fixed template such as "first answer directly, then add detail" or fixed 2-4 bullets.
- AI coaching should be natural Chinese, with AI deciding how many points and how to organize them.
- The final grammar correction section must remain present and recognizable as `语法错误纠正：...`.
- Band 7 answer generation should not be replaced by hardcoded personal-content templates when Codex fails.
- Fallback content must be transparent and must not pretend to be AI.
- P1 follow-up generation should call Codex from the previous answer when possible, then fallback only on failure.
- Remove brittle "valid_turn_band7" semantic rejection that discards plausible AI answers because keyword/relevance heuristics disagree.

## Acceptance Criteria

- [x] `turn_feedback_with_codex()` accepts plausible AI output without requiring heuristic question-aware keyword checks.
- [x] Coaching validation only requires non-empty meaningful coaching plus a grammar correction section; it must not force bullet count, fixed ordering, or max 12 lines.
- [x] `build_turn_feedback()` does not replace failed Codex Band 7 output with hardcoded P1/P2/P3 model answers pretending to be AI.
- [x] P1 work/study fallback, if ever used, preserves student + internship identity instead of forcing "software engineer".
- [x] P1 follow-up generation uses Codex when possible and stores metadata `backend=codex`; fallback is clearly marked.
- [x] Tests cover relaxed coaching format, no hardcoded work/study misclassification, and AI-backed P1 follow-up.
- [x] Existing speaking tests and full Django tests pass.

## Out of Scope

- Real Azure Speech integration.
- Real provider replacement beyond existing Codex CLI.
- Frontend redesign.
- Deleting old server.

## Technical Notes

- Main backend file: `backend_django/apps/speaking/services.py`.
- Relevant specs:
  - `.trellis/spec/backend/index.md`
  - `.trellis/spec/backend/quality-guidelines.md`
  - `.trellis/spec/backend/error-handling.md`
  - `.trellis/spec/guides/index.md`
