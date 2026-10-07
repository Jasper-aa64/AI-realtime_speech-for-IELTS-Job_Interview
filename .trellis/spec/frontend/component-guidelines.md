# Component Guidelines

> How components are built in this project.

---

## Overview

The IELTS Web UI uses plain HTML, CSS, and JavaScript under `web/static/`.
Keep the first browser surface simple, dependency-light, and easy to deploy as
a static UI served by the local/backend API server.

---

## Component Structure

- `index.html` defines stable semantic regions and controls.
- `styles.css` owns layout, responsive behavior, visual states, and typography.
- `app.js` owns mode state, API calls, timers, and rendering.
- Prefer small render/update functions over large inline DOM mutation blocks.
- Practice flows must keep stable DOM structure during a turn. State changes
  such as Listening, Preparing, Recording, and Saving should update text,
  classes, progress, and disabled state without moving the recorder control.

---

## Props Conventions

- Plain JavaScript state objects should use predictable keys:
  `mode`, `sessionId`, `questions`, `topic`, `transcripts`, `scores`, and
  `timer`.
- API request payloads should match backend endpoint names and avoid leaking
  implementation-only fields into UI state.

---

## Styling Patterns

- Use ordinary CSS classes in `styles.css`; do not add a CSS framework unless a
  later task explicitly adopts one.
- IELTS practice UI should be focused and work-like: clear panes, restrained
  color, strong timer/status areas, and readable transcript/feedback sections.
- Avoid marketing hero layouts and decorative card stacks for the core practice
  app.
- Dynamic prompt typography must have a fixed upper bound. Short P1/P3
  questions may scale up for readability, but they must not exceed the prompt
  card's professional display size or dominate the whole workspace.

---

## Accessibility

- Buttons that start/stop timers or switch modes must use actual `button`
  elements.
- A visible Exit button is required during active voice attempts. It must be a
  real button and call the shared abort/reset path, not only hide UI elements.
- Dynamic status and error text must be visible in the page, not console-only.
- Text inputs/areas for transcripts need visible labels or clear adjacent
  context.
- Color should not be the only signal for active mode, score state, or errors.

---

## Common Mistakes

- Starting a new mode without clearing prior timers or stale transcripts.
- Letting browser `speechSynthesis`, `<audio>`, MediaRecorder, or pending
  `setTimeout` callbacks continue after Exit or navigation.
- Rendering backend reports as raw JSON instead of learner-readable sections.
- Sampling questions client-side when a session-start API contract exists.
- Assuming every failed API response is valid JSON.

## Brand Identity

- Use `/assets/brand/studio-brain.svg?v=20261007-rounded-brain-2` for the
  top-left brand, AI assistant navigation, corner trigger, headers and welcome
  state. The canonical mark is the pink rounded-square body with fold lines and
  pixel eyes; do not draw a separate inline copy or add limbs / a bulb to it.
- Browser ICO, touch PNG and desktop ICNS / window PNG are generated from that
  same SVG by `scripts/generate_brand_icons.py`; regenerate those exports when
  the source changes.
- Keep the top-left `.brand-logo` square and larger than the wordmark. Place
  `.brand-bulb` absolutely, decorative and pointer-transparent, so hover, keyboard
  focus and an open workspace switcher can show it without shifting layout.
  Preserve clipping during the card morph and allow overflow after it settles.
- Limit wordmark typography rules to direct text spans excluding `.brand-logo`.
  Decorative span wrappers must never inherit wordmark clamps or clipping.
- The shared SVG owns blinking. Reduced motion disables blinking and shows
  the idea bulb statically on interaction, without popping, floating or rays
  pulsing. Raster icon exports always use the open-eye frame.
