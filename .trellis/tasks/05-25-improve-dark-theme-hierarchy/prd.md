# Improve Dark Theme Visual Hierarchy

## Problem

The current dark mode makes many buttons, panels, and report sections share nearly identical near-black surfaces. In Academic and Popular typefaces especially, the UI loses depth and scans as one flat block.

## Goals

- Keep the working IELTS Studio layout and all existing writing/report features intact.
- Improve dark-mode contrast between page background, sidebar, rails, panels, cards, chips, and buttons.
- Preserve theme identities:
  - Default dark: teal / green.
  - Academic dark: graphite with muted green-gray, not orange or brown.
  - Popular dark: blue / purple.
- Avoid adding new dependencies or changing backend/API behavior.

## Validation

- Review the actual app at `http://127.0.0.1:8082/`.
- Run `node --check web/static/app.js`.
- Run `git diff --check -- web/static/styles.css web/static/app.js web/static/index.html`.
