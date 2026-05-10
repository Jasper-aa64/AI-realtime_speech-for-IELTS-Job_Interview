# IELTS 口语模拟真实性底座修正

## Goal

Make the first implementation batch closer to the real IELTS Speaking exam without expanding scope into adaptive training, billing, or major workflow redesign. This batch focuses on correctness and trust: fix overall band rounding, make pronunciation clearly an estimate when no audio analysis is available, and tighten UI/report copy so the flow does not overclaim realism.

## What I already know

* `web/ielts_server.py` currently rounds overall band upward to the next 0.5, not to the nearest 0.5.
* The frontend already has a pronunciation estimate field, but the label still reads like a normal scored metric in several places.
* Current UI copy describes P1/P2/P3 in a simplified way that can sound more scripted than a real IELTS Speaking test.
* The history/report surfaces already separate scored vs unscored attempts, so the change can stay local to presentation and scoring math.
* Existing tests already cover scoring, history visibility, and P1/P2/P3 flows.

## Assumptions (temporary)

* Keep the current turn-count implementation for now; do not rewrite the exam engine in this batch.
* Do not add new audio analysis or a new pronunciation scoring backend.
* Chinese-standards, weak-question training, and billing work are out of scope for this batch.

## Open Questions

* None blocking for this batch.

## Requirements (evolving)

* Overall IELTS band should use nearest-0.5 rounding from the component average.
* Pronunciation should be clearly presented as an estimate / not officially assessed when no audio analysis exists.
* P1/P2/P3 copy should use realistic IELTS timing language and avoid implying the mock engine is the same as the real exam.
* Report/history surfaces should make the estimate status and backend provenance visible.
* Tests should cover the rounding rule and the label/copy changes.

## Acceptance Criteria (evolving)

* [ ] Average component scores round to the nearest 0.5, including quarter-band edge cases.
* [ ] Summary and detail views show pronunciation as an estimate or not assessed, not as a normal full score.
* [ ] P1/P2/P3 copy is updated to match real IELTS timing language and practice framing.
* [ ] Tests assert the new rounding and presentation behavior.

## Definition of Done (team quality bar)

* Tests added/updated where behavior changed
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* Adaptive weak-question training
* Billing / token deduction
* Large exam-flow redesign
* New pronunciation ML or speech-scoring models

## Technical Notes

* Backend: `web/ielts_server.py`
* Frontend: `web/static/app.js`, `web/static/index.html`
* Tests: `tests/test_ielts_web_server.py`
* Existing spec entry points: `.trellis/spec/backend/index.md`, `.trellis/spec/frontend/index.md`, `.trellis/spec/guides/index.md`
