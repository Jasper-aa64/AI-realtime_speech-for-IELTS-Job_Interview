# Refine IELTS Report Question Column Alignment

## Goal

Center only the Question column content in the IELTS report table so question cells such as `P1 1` plus the question text are visually centered, while other columns retain their natural/default alignment.

## What I Already Know

- The likely issue is in `web/static/styles.css`.
- Existing CSS may center the first `td`, but `.question-header` uses flex layout with `space-between`, preventing the `P1 1` line from appearing centered.
- `Your recording` and `Band 7 spoken version` must remain default-aligned.
- P1 wording and unrelated dirty changes are out of scope.

## Requirements

- Make the smallest CSS change needed to center Question column cell content.
- Change JavaScript only if inspection shows CSS alone cannot address the behavior.
- Do not alter report content, wording, table data shape, or unrelated styles.
- Do not revert unrelated existing edits.

## Acceptance Criteria

- [ ] Question column body content is centered, including the part/question number line and the question text.
- [ ] `Your recording` column keeps natural/default alignment.
- [ ] `Band 7 spoken version` column keeps natural/default alignment.
- [ ] If JavaScript is touched, `node --check web/static/app.js` passes.

## Out of Scope

- P1 prompt wording changes.
- Report copy changes.
- Broad table redesign.
- Cleanup of unrelated dirty files.

## Technical Notes

- Inspect `web/static/styles.css` for report table selectors and `.question-header`.
- Prefer a targeted selector for the Question column rather than broad table cell alignment changes.
