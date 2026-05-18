# Prevent Sidebar and Theme Boot Jitter

## Goal

Stop the left sidebar and typeface selector from visibly jumping during direct navigation or refresh.

## Root Cause

The previous boot fix only hid the main workspace. The static sidebar still rendered with default `首页` active and default typeface active. JavaScript then applied the URL view and stored typeface, so the sidebar selection and typeface control visibly changed after load. Typeface body classes were also applied with a 250ms delay even during initial boot.

## Requirements

- Hide the whole app shell during boot, not only the workspace.
- Apply the stored typeface immediately during boot.
- Keep the delayed typeface animation for user-initiated theme changes.
- Keep direct URL routing behavior unchanged.

## Acceptance Criteria

- [x] Direct `?view=p1Corpus` does not briefly show `首页` selected in the sidebar.
- [x] Direct `?view=p2Corpus` does not briefly show `首页` selected in the sidebar.
- [x] Stored typeface does not visibly jump after the page becomes visible.
- [x] User clicking a typeface option still updates the control normally.
- [x] JS syntax check passes.

## Technical Notes

- Main files: `web/static/styles.css`, `web/static/app.js`.
- Current boot class: `body.app-booting`.
- Current typeface function: `applyFontStyle()`.
