# history P2 report layout boxes

## Goal

Adjust the History detail P2 report layout so the P2 report heading, title/question count, overall band, calibration/feedback summary, and compact criterion scores appear in one summary box, while the turn table appears in its own separate box.

## What I already know

* The user pointed to the History page P2 report detail.
* The visible content includes `P2 report`, the cue-card title, question count, `Band 4.5`, the calibration summary, and compact FC/LR/GRA/Pron scores.
* The table should be placed in a separate box.
* The relevant frontend files are `web/static/app.js` and `web/static/styles.css`.

## Assumptions

* This is a visual grouping change only.
* P2 cue-card detail should remain near the P2 report summary rather than attached to the answer table.
* Non-P2 history reports should keep their current layout.

## Requirements

* P2 history summary content renders as a single `detail-card`.
* P2 cue-card prompt is grouped with that summary card.
* The P2 answer/report table renders in a separate card.
* Existing report data and table columns are preserved.

## Acceptance Criteria

* [ ] Opening a P2 history item shows one top box containing heading, title/question count, band, feedback summary, cue-card prompt, and score chips.
* [ ] The turn table appears below in its own bordered card.
* [ ] Mock and non-P2 reports continue to render.
* [ ] Frontend syntax checks pass.

## Out of Scope

* Backend scoring changes.
* Copy/content rewrites.
* History list behavior changes.

## Technical Notes

* `renderDetail` builds the top history detail summary.
* `turnTableSection` currently combines `cueCardHtml` and the table into one `turn-report-card`.
