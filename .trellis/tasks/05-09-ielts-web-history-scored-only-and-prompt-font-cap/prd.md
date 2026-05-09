# IELTS web history scored-only and prompt font cap

## Goal

Ensure the IELTS web history/report UI only exposes fully scored attempts, and keep short Part 1/Part 3 prompt text readable without oversized dynamic font growth.

## Requirements

- `/api/history` must include only attempts whose full required flow completed and whose status is `scored`.
- Attempts in `started`, `ready_to_score`, `aborted`, or other non-scored states must not appear as report/history entries.
- `/api/history/<attempt_id>` must not return a report-like payload for non-scored attempts; return a clear JSON error instead.
- Exiting or aborting before score generation must not leave a report-looking history entry.
- Part 1 and Part 3 short prompt dynamic font sizing should still grow for short questions but must have a reasonable maximum cap.
- Part 2 cue card readability and sizing behavior should remain unaffected.

## Acceptance Criteria

- Backend tests cover started, ready_to_score, and aborted attempts being excluded from history.
- Backend tests cover non-scored history detail being blocked with a JSON error.
- Existing scored attempt history/detail behavior continues to work.
- `web/static/app.js` passes `node --check`.
- Python server and tests pass `py_compile`.
- Unit test discovery passes.
- Existing UI verification ctest target passes.

## Out of Scope

- Redesigning the history UI.
- Changing scoring backends or score payload shape.
- Changing Part 2 cue card typography.

## Technical Notes

- Likely impacted files: `web/ielts_server.py`, `tests/test_ielts_web_server.py`, and CSS/JS under `web/static/`.
- Backend spec indexes read: `.trellis/spec/backend/index.md`, `.trellis/spec/frontend/index.md`.
