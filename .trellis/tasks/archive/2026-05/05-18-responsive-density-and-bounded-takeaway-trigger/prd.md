# Responsive Density And Bounded Takeaway Trigger

## Goal

Make the app feel correctly scaled at 100% browser zoom on smaller desktop/laptop screens while preserving the current wide-screen layout, and make the selected-text translate trigger behave like a bounded circular floating control.

## Scope

- Add desktop compact density rules for narrower/lower laptop viewports.
- Keep wide desktop layout visually unchanged.
- Reduce sidebar, workspace, home, corpus, and takeaway spacing only under compact desktop breakpoints.
- Make the selected-text trigger circular with clear visual affordance.
- Show the trigger only after selection is completed, not during the drag.
- Clamp the trigger inside the viewport.
- Bump static asset version.

## Acceptance Criteria

- [x] Wide desktop keeps current 100% scale.
- [x] 13/14-inch laptop effective widths render less crowded at 100% zoom.
- [x] Sidebar and workspace spacing compact under desktop breakpoints.
- [x] Home, corpus, and takeaway pages have smaller cards/headings in compact desktop.
- [x] Selected-text trigger is circular.
- [x] Trigger appears after selection completion.
- [x] Trigger cannot be positioned outside the viewport.
- [x] JS syntax check passes.
