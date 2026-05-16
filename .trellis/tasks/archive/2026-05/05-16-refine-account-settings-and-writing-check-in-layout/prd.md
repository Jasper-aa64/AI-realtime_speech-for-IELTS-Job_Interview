# Refine account settings and writing check-in layout

## Goal

Make the post-migration web UI feel closer to normal app conventions: account authentication should not occupy the Settings surface, Settings should return to wallet and weak-question records, and the Writing check-in card should use the full vertical space with calendar content anchored high and save/score controls anchored low.

## Requirements

* Move login/register/account profile controls out of the Settings panel.
* Add a dedicated login/register account surface reachable from the global account/status area.
* Keep Settings focused on wallet and weak-question training records.
* Preserve existing authentication, profile sync, logout, wallet, and training behavior.
* Stretch the writing check-in card to the full height of the writing editor area.
* Keep calendar stats and month grid near the top of the right card.
* Keep word count, save status, save button, AI score button, and AI scoring note near the bottom of the right card.
* Avoid backend changes.

## Acceptance Criteria

* [x] Settings no longer shows account login/register/profile controls.
* [x] A dedicated account page/panel allows login, registration, logout, and saving names.
* [x] Existing Settings entry still opens wallet and weak-question training records.
* [x] Account controls do not consume Settings vertical space.
* [x] Writing check-in card fills the available right-column height on desktop.
* [x] Writing calendar content is visually grouped at the top.
* [x] Writing save/score controls and note are visually grouped at the bottom.
* [x] `node --check web/static/app.js` passes.
* [x] Django tests pass or unaffected by frontend-only change.

## Out of Scope

* Backend auth changes.
* New account recovery/password reset flow.
* Production deployment changes.
