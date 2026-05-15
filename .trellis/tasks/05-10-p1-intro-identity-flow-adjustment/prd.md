# P1 Intro Identity Flow Adjustment

## Goal

Adjust IELTS Web Part 1 attempt generation so the first turns follow the exam-like identity flow: ask the candidate name first, then ask whether they work or study, before continuing with ordinary Part 1 questions.

## Requirements

- P1 starts with a fixed name turn followed by a fixed work/study identity turn.
- The ordinary random Part 1 pool must not include duplicate scattered work/study identity prompts.
- P1 practice remains exactly 10 turns total.
- Mock mode keeps the existing P1 count behavior before P2/P3 flow and remains compatible with voice-first playback, `auto_play_question`, and score-after-completion behavior.
- Turn/prompt metadata may express `intro`, `name`, and `work_study` flow roles.
- After the work/study identity answer, the server generates one answer-aware
  follow-up for work, university major/study, school, or other current status.
- The identity follow-up reuses the existing voice-first next-turn flow and is
  marked as a follow-up in turn metadata, but it does not count against the 10
  main P1 questions.
- No new frontend input fields are required.
- Update `tests/test_ielts_web_server.py` to verify P1 start ordering and exclusion of duplicate random work/study prompts.
- Do not modify unrelated files and do not commit.

## Acceptance Criteria

- `POST /api/attempts/start` for `p1` returns 10 turns.
- The first turn asks for the candidate's name and has prompt metadata marking the intro/name role.
- The second turn asks whether the candidate works or studies and has prompt metadata marking the intro/work_study role.
- Remaining P1 random turns do not contain the existing scattered work/study identity wording.
- Completing the work/study identity turn returns a generated follow-up as
  `next_turn`; that follow-up is not included in the initial 10 main P1 turns
  and has metadata marking it as a follow-up.
- Existing completion and scoring flow for P1 remains covered by tests.

## Out of Scope

- Frontend form/input changes.
- CLI Part 1 flow changes.
- Question-bank data edits unless required by tests.
- Git commit.

## Technical Notes

- Main implementation target: `web/ielts_server.py`.
- Test target: `tests/test_ielts_web_server.py`.
- Relevant spec: `.trellis/spec/backend/quality-guidelines.md` IELTS Web API Boundary.
