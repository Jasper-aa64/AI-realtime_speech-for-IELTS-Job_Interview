# Fix P1 Report Missing Fields Display

## Goal

Fix the P1 report generated at `2026-05-29 13:13` and the underlying report/display path so per-question report sections are complete in the UI. The report currently has overall scoring and overall review, but each turn is missing the expected AI-generated `Band 7 spoken version` and `AI coaching` content.

## What I Already Know

* The user is referring to the report:
  * attempt id: `80f4d79f40934d7e81d4bc5244b37cdc`
  * title: `Part 1 practice`
  * report created: `2026-05-29 13:13:31.680474`
  * overall band: `5`
* The report payload contains overall scoring fields:
  * `overall_band`
  * `fluency_coherence`
  * `lexical_resource`
  * `grammar_range_accuracy`
  * `overall_review`
  * `feedback_summary`
* The report payload contains 12 turns, but every scored answer turn is effectively incomplete:
  * `feedback_generation_status` is `pending`
  * `feedback_generation_backend` is `codex`
  * `model_audio.status` is `pending`
  * `band7_version` / `band7_markdown` are absent or empty
  * `ai_coaching` is absent or empty
* The first name-intro turn has no transcript and should not be treated as a missing answer.
* This is not only a UI issue. The backend report payload is missing per-turn AI content, so the frontend has nothing meaningful to render.

## Requirements (Evolving)

* For this specific P1 report, missing per-turn fields must be filled or regenerated so the UI shows complete per-question content.
* The fix must preserve honesty:
  * if Codex succeeds, mark backend/status as `codex` / `ready`;
  * if Codex fails, do not show fake generic AI content as if it succeeded.
* The UI must visibly distinguish:
  * ready AI coaching,
  * pending generation,
  * failed generation with retry action.
* The report detail endpoint should return enough per-turn fields for the frontend:
  * transcript,
  * Band 7 answer plain/markdown,
  * AI coaching,
  * generation backend/status/error,
  * model audio status if available.
* The fix should apply to future P1 reports, not only patch this one record manually.

## Acceptance Criteria (Evolving)

* [ ] The `2026-05-29 13:13 Band 5` P1 report displays per-question content in the UI.
* [ ] Answer turns with transcripts show either generated Band 7 answer + AI coaching, or an explicit pending/failed state.
* [ ] The backend payload for completed AI turns includes non-empty `band7_version` or `band7_markdown`.
* [ ] The backend payload for completed AI turns includes non-empty `ai_coaching`.
* [ ] Existing report list/detail behavior remains intact.
* [ ] No local `backend_django/db.sqlite3` changes are committed.

## Out of Scope

* Rewriting the whole speaking scoring architecture.
* Adding fake fallback content that pretends to be AI.
* Editing deprecated `web/ielts_server.py`.

## Technical Notes

* Likely backend file: `backend_django/apps/speaking/services.py`.
* Likely frontend file: `web/static/app.js`.
* Existing render path references:
  * history detail loading around `loadHistory`, `fetchHistoryDetail`, and report rendering in `web/static/app.js`.
  * report payload generation and turn serialization in `backend_django/apps/speaking/services.py`.
* Database inspection shows this is a payload-generation/completion problem before it is a visual rendering problem.
