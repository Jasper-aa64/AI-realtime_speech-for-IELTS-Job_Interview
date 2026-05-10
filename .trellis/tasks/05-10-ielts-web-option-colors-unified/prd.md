# IELTS Web Option Colors Unified

## Goal
Unify the top navigation and history card tones in the IELTS web UI so the four modes use one consistent palette:
- Mock: black
- P1: green
- P2: blue
- P3: purple

## Problem
The current UI uses separate tone/active styles for the top navigation and history items. Users can see inconsistent colors between the top option cards and the history rail/cards.

## Scope
- `web/static/app.js`
- `web/static/styles.css`

## Requirements
- Keep the existing layout and interaction model.
- Ensure the top nav buttons and history cards share the same tone mapping.
- Ensure mock is explicitly black, not a default neutral.
- Keep hover and active states visually consistent across both surfaces.
- Do not touch backend behavior.

## Acceptance Criteria
- Top nav and history cards use the same mock/p1/p2/p3 tone classes.
- Mock is black in both nav and history.
- P1 is green, P2 is blue, P3 is purple.
- No broken or duplicated template strings are introduced.
- The page still loads and switches views normally.
