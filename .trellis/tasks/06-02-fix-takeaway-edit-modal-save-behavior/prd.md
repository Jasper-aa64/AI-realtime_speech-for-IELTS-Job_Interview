# Fix Takeaway Edit Modal Save Behavior

## Goal

Fix the Takeaway card edit modal so it feels compact, persists edits reliably, and treats blank backdrop clicks as save-and-close instead of cancel.

## What I Already Know

- User reports the Takeaway edit modal from the previous implementation is too large.
- Edits appear not to persist, or the Save action appears ineffective.
- Clicking the blank backdrop should autosave dirty edits and close only after save succeeds.
- Scope is limited to `web/static/corpus-takeaway.js`, related frontend files if needed, and backend only if the save bug is backend-side.
- Unrelated P1, audio, and AI code must not be touched.

## Requirements

- Make the Takeaway edit dialog compact and card-like rather than full-screen huge.
- Keep edit textareas smaller, with reasonable max height and scroll behavior.
- Ensure Save persists both `source_text` and `chinese_text`.
- Verify the frontend PATCH payload field names match the backend endpoint.
- Refresh the visible card/list immediately after a successful save.
- Backdrop/blank click must autosave if the dialog is dirty, then close.
- If backdrop autosave fails, keep the dialog open and show an error.
- Keep any existing explicit Cancel/no-save UX if present.

## Acceptance Criteria

- [ ] Takeaway edit modal renders as a compact centered card on desktop and mobile.
- [ ] `source_text` and `chinese_text` edits persist through the PATCH endpoint.
- [ ] The edited card/list content updates immediately after save without requiring a manual refresh.
- [ ] Dirty backdrop click saves before close; save failure leaves the modal open with visible error.
- [ ] Explicit cancel remains a no-save action if present.
- [ ] No unrelated P1/audio/AI code is changed.

## Definition of Done

- Relevant lightweight checks are run.
- Changed files are limited to the Takeaway edit/save path unless backend verification shows otherwise.
- No commit or push is performed.

## Out of Scope

- P1 flow changes.
- Audio/ASR/playback changes.
- AI generation or scoring changes.
- Broader UI redesign beyond the Takeaway edit modal.

## Technical Notes

- Inspect `web/static/corpus-takeaway.js` first for modal rendering and PATCH payload behavior.
- Inspect backend speaking/corpus endpoint only if frontend payload or persistence is unclear.
