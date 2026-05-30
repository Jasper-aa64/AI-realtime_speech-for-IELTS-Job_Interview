# remove account weak training panel

## Goal

Remove the temporary weak-training review module from the account page UI and tighten the account page vertical layout so the account screen opens directly into the two primary columns: profile and wallet.

## What I already know

- The current account page renders three cards in `web/static/index.html`: profile, wallet, and `account-weak-card`.
- The weak-training card is populated by `loadWeakTraining()` in `web/static/app.js` via `/api/training/weak-items`.
- The visible issue is twofold: the header/hero area leaves too much blank vertical space, and the bottom weak-training/review panel should temporarily disappear.
- Existing frontend spec already says weak training should stay out of attempt reports; this task only removes it from the account page UI.

## Requirements

- Remove the account-page `Review / 弱题训练` card from the visible UI.
- Keep the page as a two-column layout: profile and wallet.
- Stop loading weak-training data when entering the account page.
- Remove skeleton/status updates for DOM nodes that no longer exist.
- Reduce account page top/header spacing so the two columns appear higher on first open.
- Preserve account profile, password, logout, wallet, ledger, recharge, and dark mode behavior.

## Acceptance Criteria

- [x] Account profile page shows only profile and wallet cards in the main grid.
- [x] No visible `Review`, `弱题训练`, weak-training count, or weak-training list remains on the account page.
- [x] Opening account page no longer calls `/api/training/weak-items` from `loadAccountProfile()`.
- [x] Top whitespace is reduced compared with the screenshot while keeping the header readable.
- [x] `node --check web/static/app.js` passes.

## Out of Scope

- Do not delete backend training APIs.
- Do not remove training data models or reports.
- Do not change speaking/writing practice behavior.
- Do not redesign account auth flow.

## Technical Notes

- Likely files: `web/static/index.html`, `web/static/app.js`, `web/static/styles.css`.
