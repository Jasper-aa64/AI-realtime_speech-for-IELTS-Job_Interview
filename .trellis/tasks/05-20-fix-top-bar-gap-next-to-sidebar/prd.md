# Fix Top Bar Gap Next To Sidebar

## Goal

Remove the visible empty global topbar strip next to the fixed sidebar on desktop. The avatar/account action should remain usable, but the blank bar/gutter should not read as a layout gap.

## Requirements

- Keep sidebar width and main workspace layout unchanged.
- Keep avatar/account button accessible in the top right.
- Do not affect mobile layout where `.global-topbar` is hidden.
- Remove the writing page's redundant page title so the editor gets more vertical space.
- Keep Writing Task 1/Task 2, prompt picker, and random prompt controls in the global topbar next to the avatar.
- Keep change scoped to frontend static files.

## Acceptance Criteria

- [x] No visible blank topbar strip appears between sidebar and content on desktop.
- [x] Avatar button remains visible and clickable.
- [x] `node --check web/static/app.js` passes.
- [x] Writing view no longer shows the large "每日写作" title block.
- [x] Writing task/prompt/random controls live in the global topbar rather than inside the editor body.
