# Increase Language Takeaway Popup Typography

## Goal

Make the Language Takeaway popup easier to read by increasing the typography size for the source and Chinese editing areas.

## Requirements

- Increase `原文` and `中文` label size in the Language Takeaway popup.
- Increase textarea text size for both original and Chinese content.
- Keep the popup layout stable and usable at current width.
- Do not change vocabulary cards or other pages.

## Acceptance Criteria

- [x] Popup labels are visibly larger.
- [x] Popup textarea content is visibly larger.
- [x] Existing popup interaction remains unchanged.
- [x] CSS/JS syntax checks pass where relevant.

## Technical Notes

- Main file: `web/static/styles.css`.
- Existing selectors: `.language-takeaway-popup label`, `.language-takeaway-popup textarea`.
