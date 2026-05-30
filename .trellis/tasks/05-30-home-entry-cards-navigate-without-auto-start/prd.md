# Home entry cards navigate without auto start

## Goal

The four speaking entry cards on the home page should only navigate to their
corresponding practice screens. They must not immediately start a recording
attempt.

## What I Already Know

- The home cards are anchors in `web/static/index.html` with `href="?view=p1"`,
  `href="?view=p2"`, `href="?view=p3"`, and `href="?view=mock"`.
- `web/static/app.js` currently intercepts `[data-home-mode]` clicks and calls
  `startPracticeMode()`.
- `startPracticeMode()` switches view and then calls `startPractice()` for all
  modes except P3.
- The user wants the cards to only switch screens.

## Requirements

- Clicking `P1 短问短答` on the home page navigates to the P1 page only.
- Clicking `P2 Cue Card` on the home page navigates to the P2 page only.
- Clicking `P3 深入讨论` on the home page navigates to the P3 page only.
- Clicking `完整 Mock` on the home page navigates to the Mock page only.
- Existing start controls inside the destination pages keep their current
  behavior.
- New-tab behavior from anchor clicks remains intact.

## Acceptance Criteria

- [x] Home card click handlers no longer call `startPractice()`.
- [x] Home card click handlers no longer call `startPracticeMode()` if that
      function auto-starts attempts.
- [x] `?view=p1`, `?view=p2`, `?view=p3`, and `?view=mock` still work as direct
      links.
- [x] `node --check web/static/app.js` passes.

## Out of Scope

- Redesigning the home page.
- Changing practice page start buttons.
- Changing attempt creation APIs.

## Technical Notes

- Likely implementation point: `bindEvents()` in `web/static/app.js`.
- The existing `startPracticeMode()` function may become unused or should be
  changed only if no other call site depends on auto-start behavior.
