# Brainstorm Direct P2 Practice and Particle Decoration

## Goal

Let learners launch the expanded Brainstorm question directly into a new-tab P2 practice, and add a restrained animated square-particle decoration to the Brainstorm entry card.

## Requirements

- Add a small circular play button immediately left of `编辑正文` in the expanded cue requirements header.
- Use a real play icon asset and center it precisely in a fixed-size button.
- Open a new tab with the selected P2 cue ID and automatically start that exact P2 practice.
- Keep the current Brainstorm dialog and unsaved input untouched.
- Reuse MIT-licensed particles.js for a compact square-particle visual inside the Brainstorm entry card.
- The decoration must not increase card height, cover text, or capture pointer events.
- Support light/dark themes and disable movement for reduced-motion users.

## Acceptance Criteria

- [ ] Clicking the play button opens `?view=p2&p2_cue_id=<id>&autostart=1` in a new tab.
- [ ] The new tab pins the cue and calls the existing P2 start flow.
- [ ] The button remains a perfect circle and the play icon is visually centered.
- [ ] Brainstorm card text remains readable over the particle canvas.
- [ ] Particle decoration initializes once and does not block card clicks.
- [ ] JS syntax, focused Node tests, and Django check pass.

## Out of Scope

- Changing the existing P2 card practice button.
- Using the provided screenshot as an asset.
- Changing Brainstorm autosave or editor-return behavior.

