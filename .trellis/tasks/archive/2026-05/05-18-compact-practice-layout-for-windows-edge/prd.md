# Compact Practice Layout For Windows Edge

## Goal

Fix the practice page density on Windows Edge at 100% zoom so P1/P2/P3 practice screens do not look oversized or crowded on laptop-sized viewports.

## Problem

The previous compact desktop pass improved navigation, home, corpus, and takeaway surfaces, but practice mode still uses wide-screen sizing for prompt cards and the recording control. On Windows Edge at 100% zoom the prompt text and Start circle are too large.

## Scope

- Add compact desktop sizing for practice page title/subtitle.
- Reduce practice grid gap and card padding under compact desktop breakpoints.
- Reduce prompt card font sizes and min heights under compact desktop breakpoints.
- Reduce recorder card min height, timer, recording circle, icon, and labels under compact desktop breakpoints.
- Bump static asset version.

## Acceptance Criteria

- [x] Windows Edge 100% laptop view has smaller prompt text.
- [x] Recording Start circle is smaller in compact desktop mode.
- [x] Practice cards fit better vertically without requiring browser 90% zoom.
- [x] Wide desktop remains unchanged outside compact breakpoint.
- [x] Mobile rules remain unchanged.
- [x] JS syntax check passes.
