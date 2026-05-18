# Redesign Home Landing Practice Entry Page

## Goal

Make `首页` a real landing page instead of using the Mock practice panel as the default first screen. The home page should provide clean entry points for P1, P2, P3, and Mock, while the practice runtime UI only appears after a user chooses a practice mode.

## What I Already Know

- Current default state is `view: "mock"`.
- The left sidebar starts with `Mock`, not `首页`.
- `mockHomePanel` is nested inside `practicePanel`, so the Mock answering UI remains part of the first-screen DOM and can appear below the landing content.
- `viewCopy.mock` currently shows `Practice flow: P1, P2, then P3 generated from your P2 answer.`, which the user explicitly wants removed.
- The app uses plain `web/static/index.html`, `web/static/app.js`, and `web/static/styles.css`.

## Requirements

- Add a real left-sidebar `首页` navigation item.
- Make `首页` the default view.
- Redesign the home page with four clear entry points: P1, P2, P3, and Mock.
- Do not show the Mock/practice answering surface under the home page.
- Redesign `语料库` and `生词本` using the same visual language as the new home page.
- Add an icon to the `隐藏中文`/`显示中文` control.
- Keep existing P1/P2/P3/Mock runtime behavior unchanged after entry.
- Keep authentication gate behavior unchanged when starting practice.

## Acceptance Criteria

- [x] Sidebar contains `首页` as the first primary item.
- [x] First load lands on the home page, not Mock.
- [x] Home title/subtitle no longer say `Mock` or `Practice flow: P1, P2, then P3 generated from your P2 answer.`
- [x] Home shows P1, P2, P3, and Mock entry controls.
- [x] Clicking each entry switches to the corresponding practice mode and starts the existing practice flow.
- [x] `practicePanel` is hidden on `home`.
- [x] `mockHomePanel` no longer controls the default landing screen.
- [x] `语料库` cards no longer stretch into large empty columns and match the home card style.
- [x] `生词本` has a matching header/card style and an icon-bearing hide/show Chinese toggle.
- [x] JS syntax check passes.

## Out of Scope

- Backend/API changes.
- Changing the actual recorder/session/scoring flow.
- Changing account, corpus, writing, or reports views.

## Technical Notes

- Main files: `web/static/index.html`, `web/static/app.js`, `web/static/styles.css`.
- Relevant frontend spec: plain HTML/CSS/JS, stable practice DOM during active attempts, actual buttons for mode changes.
