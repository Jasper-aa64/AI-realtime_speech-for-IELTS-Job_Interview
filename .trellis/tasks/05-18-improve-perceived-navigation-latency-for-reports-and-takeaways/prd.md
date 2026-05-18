# Improve Perceived Navigation Latency for Reports and Takeaways

## Goal

Make report switching, report page navigation, and vocabulary book loading feel immediate instead of blank/loading-blocked.

## Root Cause

Several views clear visible content and wait for API responses before showing useful UI. History/report detail selection also refetches detail each time without showing an already-loaded copy first. This is correct for freshness but creates a slow/click-lag feeling.

## Requirements

- Reuse in-memory loaded data immediately when revisiting `生词本`, `口语报告`, and `写作报告`.
- For report detail tabs, render cached detail immediately if available, then refresh in the background.
- Avoid global blocking busy overlay for writing reports when existing data can remain visible.
- Keep server as source of truth; cache is only session-level UI acceleration.
- Preserve existing fresh fetch behavior in the background.

## Acceptance Criteria

- [x] Revisiting `生词本` with existing items keeps the list visible while refreshing.
- [x] Revisiting `口语报告` with existing list keeps the list visible while refreshing.
- [x] Clicking an already-viewed口语报告 renders instantly from cache and refreshes detail.
- [x] Revisiting `写作报告` with existing list/detail keeps visible content while refreshing.
- [x] Clicking an already-viewed写作报告 renders instantly from cache and refreshes detail.
- [x] JS syntax check passes.

## Technical Notes

- Main file: `web/static/app.js`.
- Use session memory only; no localStorage persistence.
- Keep stale-then-refresh simple and scoped.
