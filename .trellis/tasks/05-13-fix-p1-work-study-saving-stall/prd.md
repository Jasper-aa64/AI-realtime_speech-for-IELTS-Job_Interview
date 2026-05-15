# Fix P1 Work/Study Saving Stall

## Goal

Completing the Part 1 "Do you work or do you study?" turn should return quickly and advance the flow with a deterministic identity follow-up instead of blocking the request while Codex generates a custom follow-up or examiner TTS.

## What I Already Know

- The request path is `handle_turn_complete -> insert_p1_identity_follow_up`.
- `insert_p1_identity_follow_up` currently calls `generate_p1_identity_follow_up()`, which may call `run_codex` for up to 45 seconds.
- `handle_turn_complete` also calls `ensure_examiner_tts` synchronously for the next turn.
- The allowed ownership for this fix is `web/ielts_server.py` and focused tests in `tests/test_ielts_web_server.py`.

## Requirements

- Insert a P1 identity follow-up synchronously using `fallback_p1_identity_follow_up(answer)`.
- Do not call Codex or `generate_p1_identity_follow_up()` on the turn-completion request path.
- Avoid synchronous examiner TTS for the inserted/next turn on this request path.
- Preserve enough existing P1 flow behavior for the response to include a `next_turn` follow-up.
- Keep the change conservative and scoped.

## Acceptance Criteria

- [ ] Completing the work/study turn returns a next-turn follow-up.
- [ ] A focused test proves `run_codex` and `generate_p1_identity_follow_up` are not called synchronously during completion.
- [ ] Targeted unittest and Python compile checks pass.

## Out of Scope

- Broad async job infrastructure.
- Frontend changes.
- Refactoring unrelated P1/P2/P3 flow.

## Technical Notes

- Relevant backend guidance: IELTS Web API boundary requires deterministic fallback behavior and background per-turn feedback failures must keep the speaking flow moving.
