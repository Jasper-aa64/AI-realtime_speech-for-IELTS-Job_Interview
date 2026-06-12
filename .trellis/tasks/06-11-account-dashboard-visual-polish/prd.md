# Account dashboard visual polish

## Goal

Improve the account dashboard visual hierarchy without changing product behavior. The page should feel like a polished account/control surface: compact top header, clearer profile card, cleaner question-bank selector, and wallet balance/CTA grouped as one coherent module.

## What I already know

- User highlighted three rough areas in the account page screenshot:
  - Floating back button and oversized top account header.
  - Question-bank selector card inside the profile card.
  - Wallet balance card where recharge/status controls look bolted on.
- The account page is rendered in `web/static/index.html`.
- Wallet balance HTML is generated dynamically in `web/static/app.js`.
- Most visual behavior is controlled by many historical final overrides in `web/static/styles.css`.
- This task should not change billing, account, question-bank, or auth behavior.

## Requirements

- Make the top account header more compact and aligned.
- Make the back button visually lighter and less detached.
- Keep the account title, account detail, password, and logout actions visible.
- Make the question-bank selector read like a compact clickable setting instead of a large empty feature card.
- Preserve the question-bank selector click target and dialog behavior.
- Group wallet amount, recharge CTA, AI availability, and hint in one balanced card.
- Keep ledger rows readable and aligned.
- Preserve dark-mode readability.
- Avoid changing backend APIs or account/wallet business logic.

## Acceptance Criteria

- [ ] Account page header no longer reads as a large empty bordered block.
- [ ] Back button aligns with the account surface and does not dominate the page.
- [ ] Question-bank selector is compact, readable, and still opens the selector dialog.
- [ ] Wallet balance card has a coherent right-side action/status group.
- [ ] Dark mode remains readable.
- [ ] `node --check web/static/app.js` passes.
- [ ] Django `manage.py check` passes.

## Out of Scope

- No backend behavior changes.
- No account auth redesign.
- No wallet ledger logic changes.
- No question-bank scope logic changes.
- No changes to speaking/writing practice flows.

## Technical Notes

- Main HTML: `web/static/index.html`.
- Main CSS: `web/static/styles.css`.
- Wallet dynamic render: `renderWalletPayload()` and `resetAccountProfileLoadingUi()` in `web/static/app.js`.
- Prefer a final, scoped account-page override over editing many older historical override blocks.
