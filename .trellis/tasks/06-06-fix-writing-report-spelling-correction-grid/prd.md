# Fix Writing Report Spelling Correction Grid

## Goal

Make the writing report spelling correction section use the available horizontal space better.

## Requirements

- Display spelling correction chips/cards in a three-column grid on desktop.
- Keep cards aligned and visually consistent; avoid rows with uneven card widths.
- Preserve existing spelling correction content and behavior.
- Keep responsive fallbacks for narrower screens.

## Non-goals

- Do not change scoring, AI report generation, or spelling extraction logic.
- Do not change database models or API payloads.
- Do not redesign unrelated writing report sections.

## Verification

- `node --check web/static/app.js`
- `git diff --check`
- Visual check that the writing report spelling correction section shows three aligned cards per row on desktop.
