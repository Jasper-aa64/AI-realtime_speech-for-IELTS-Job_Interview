# Fix Language Takeaway Popup Sizing And Bounds

## Goal

Make the Language Takeaway popup readable without feeling oversized, and keep it fully inside the browser viewport even when opened or dragged near an edge.

## Scope

- Reduce popup textarea font size from the oversized display style.
- Keep source and Chinese text clearly readable.
- Clamp popup placement when opened from a selected phrase.
- Clamp popup position while dragging.
- Update static asset version so browsers load the fix.

## Acceptance Criteria

- [x] Popup source/chinese textarea text is smaller than the current oversized screenshot.
- [x] Popup still has readable labels and editable fields.
- [x] Popup opening near right/bottom edges stays fully visible.
- [x] Dragging the popup cannot move it outside the viewport.
- [x] JS syntax check passes.
