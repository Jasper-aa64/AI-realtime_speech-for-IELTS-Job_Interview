# Merge settings into account profile layout

## Goal

Remove the separate Settings page and make Account the only place for profile, security, wallet, and weak-training records. Organize the signed-in account page with a clean two-column layout similar to the old server dashboard pattern.

## Requirements

* Remove Settings from primary navigation and app view flow.
* Account profile remains the entry from the avatar.
* Move wallet and weak-training sections below/alongside account profile content.
* Use a two-column desktop layout:
  * left: profile identity and security actions
  * right: wallet and weak-training records
* Keep mobile layout single column.
* Preserve wallet recharge dialog and weak-training loading behavior.
* Keep unauthenticated gate behavior.

## Acceptance Criteria

* [x] No Settings navigation button is shown.
* [x] No standalone Settings view is used for wallet/weak training.
* [x] Account profile loads wallet, weak-items, and replay queue when authenticated.
* [x] Account page is visually organized in two columns on desktop.
* [x] Mobile remains readable in one column.
* [x] `node --check web/static/app.js` passes.
* [x] Django tests pass.

## Out of Scope

* Backend auth changes.
* New wallet or training APIs.
* Social/SMS/email provider integration.
