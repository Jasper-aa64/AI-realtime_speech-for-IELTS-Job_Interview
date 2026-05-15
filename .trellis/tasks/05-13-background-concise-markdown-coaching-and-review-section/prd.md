# Background concise Markdown coaching and review section

## Goal

Make IELTS report coaching faster and easier to read by shortening per-turn coaching, formatting AI coaching as Markdown with clear paragraph breaks, moving heavy per-turn coaching out of the blocking scoring path where practical, and adding an overall review section based on the learner profile.

## What I already know

* Per-turn coaching is currently long and often appears as one dense paragraph.
* The frontend report renderer already has Markdown rendering support through `renderMarkdown`.
* The backend currently generates per-turn coaching inside scoring/report construction.
* The user wants each turn's coaching to be shorter, backgrounded where possible, and visually readable.
* The user wants a final overall section summarizing this attempt, using the learner profile, with comments and review points.

## Requirements

* Per-turn coaching should be concise, formatted in Markdown, and readable after frontend rendering.
* Per-turn coaching should avoid long unbroken paragraphs and use clear headings/bullets.
* Expensive per-turn coaching should not block the core score/report more than necessary.
* The report should include an overall review section based on the current attempt and learner profile.
* The overall review should include a short comment and actionable review points.

## Acceptance Criteria

* [x] Per-turn coaching prompt/output contract asks for concise Markdown.
* [x] Report UI renders per-turn coaching Markdown with paragraph/list spacing.
* [x] Report UI renders an overall review section when available.
* [x] Backend produces an overall review payload for scored attempts.
* [x] Blocking analysis path avoids duplicated per-turn coaching generation.
* [x] Relevant tests pass or failures are documented.

## Out of Scope

* Full job queue infrastructure.
* Replacing scoring model/provider.
* Changing IELTS score calculation.
* Reworking Saving upload/transcription/Azure flow in this task.

## Technical Notes

* Likely files: `web/ielts_server.py`, `web/static/app.js`, `web/static/styles.css`, `tests/test_ielts_web_server.py`.
