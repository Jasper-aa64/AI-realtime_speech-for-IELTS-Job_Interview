# Update IELTS P1 First Question Wording

## Goal

Change the fixed IELTS web Part 1 work/study intro question to exactly match the requested wording.

## Requirements

- Replace the current P1 work/study intro question with exactly: `Do you work or do you study?`
- Keep the existing P1 intro flow, prompt metadata, report/coaching behavior, and audio behavior unchanged.
- Update focused tests only if they assert the old wording.

## Acceptance Criteria

- [ ] New P1 attempts expose `Do you work or do you study?` for the fixed work/study intro turn.
- [ ] The old wording no longer appears in the source/test assertion for this fixed turn.
- [ ] Focused grep and relevant test pass.

## Out of Scope

- Report layout, coaching content, audio startup, history behavior, and unrelated dirty workspace changes.

## Technical Notes

- Likely source: `web/ielts_server.py`.
- Existing assertion found in `tests/test_ielts_web_server.py`.
