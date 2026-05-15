# Adjust IELTS Report Table Alignment

## Goal

Keep the IELTS report table readable by centering only the `Question` column while leaving `Your recording` and `Band 7 spoken version` cells in their natural text alignment.

## What I Already Know

- The user wants a minimal CSS/JS/test change.
- The P1 intro wording must keep `What is your full name?` as the first intro question and use `Do you work or do you study?` as the second intro question.
- The likely affected file is `web/static/styles.css`; JavaScript should only change if the wording verification shows a problem.
- The relevant report table headers are `Question`, `Your recording`, and `Band 7 spoken version`.

## Requirements

- Center only the content in the report table `Question` column.
- Do not center the `Your recording` or `Band 7 spoken version` columns via the report table CSS.
- Verify the P1 wording remains correct.
- Avoid reverting unrelated dirty changes.

## Acceptance Criteria

- [ ] Report table question cells are centered.
- [ ] Non-question report table columns keep default/natural text alignment.
- [ ] P1 intro wording grep confirms the expected first and second questions.
- [ ] Relevant checks are run.

## Out of Scope

- Redesigning the report table.
- Changing report payload shape or backend scoring behavior.
- Changing unrelated history/report layout styles.

## Technical Notes

- Frontend web conventions are in `.trellis/spec/frontend/quality-guidelines.md` and `.trellis/spec/frontend/component-guidelines.md`.
