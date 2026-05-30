# Restore Colorful Appearance Theme States

## Goal

Restore the visual personality of the appearance themes after the previous dark-mode safety pass flattened the UI. The third/popular theme should keep its colorful/rainbow feeling, and buttons/record controls should show meaningful color changes across states while remaining readable in dark mode.

## What I Already Know

- The sidebar label has been renamed from `Typeface` to `Appearance`, which is the intended direction.
- The previous CSS pass made dark-mode controls readable but over-normalized theme colors.
- The user specifically called out that the third theme lost its rainbow/colorful identity and that stateful controls no longer visibly change by status.
- Existing CSS has many older theme blocks, so the safest low-risk fix is a final scoped override near the end of `web/static/styles.css`.

## Requirements

- Keep `Appearance` as the control label.
- Restore distinct theme identity:
  - default dark: deep teal/green accent, readable.
  - academic dark: warm brown accent, readable.
  - popular dark: vivid blue/purple/rainbow accent, not flat dark blue only.
- Restore stateful color changes for `.record-control` states including loading/preparing, recording, processing/scoring, examiner_playing/turn_saved, and analysis_failed where available.
- Keep dark-mode button text readable; do not return to green background + black text.
- Avoid touching product logic or tests.

## Acceptance Criteria

- [ ] Appearance switcher has three centered, non-drifting buttons.
- [ ] Popular theme active state visibly uses a colorful/rainbow gradient.
- [ ] Popular theme primary action buttons keep a colorful gradient rather than flat dark blue.
- [ ] Record control dark states visibly change color by status.
- [ ] `git diff --check` passes for touched files.

## Out of Scope

- Reworking navigation structure.
- Changing theme persistence logic.
- Editing backend code.
- Committing or pushing.

## Technical Notes

- Relevant spec: `.trellis/spec/frontend/quality-guidelines.md`
- Main target: `web/static/styles.css`
