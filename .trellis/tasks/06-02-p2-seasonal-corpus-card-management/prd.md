# P2 seasonal corpus card management

## Goal

Rework the P2 corpus library so user-owned reusable material categories remain cross-season assets, while the current speaking season cue-card bank is shown as a separate management section below. The page should keep the existing category entrances at the top (人物、地点、事件、物品、特殊题目素材), then show current-season P2 cue cards below. Each cue card should be manageable like the P1 corpus library, with two clear entry points: `正文` for prepared answer material and `P3 追问` for related follow-up material.

## What I Already Know

- The project already has a current-season P2 bank in `data/ielts/part2/2026_may_august_topics.json`.
- `QuestionBank.part2_for_scope(current)` already filters current season topics.
- `/api/p2-corpus` currently returns:
  - `categories`: user-saved P2 material grouped by category.
  - `current_part2_categories`: category counts derived from current-season topics.
  - It does **not** return the current-season cue cards themselves as manageable corpus targets.
- `P2CorpusEntry` already supports:
  - `material_text` for main answer material.
  - `metadata.p3_follow_up_text` for P3 follow-up material.
  - stable IDs based on `linked_question`.
- Existing frontend P2 corpus UI in `web/static/corpus-takeaway.js` renders saved user material, not all current-season cue cards.
- The public IELTS BRO snapshot downloaded in `.firecrawl/ieltsbro-api/` is useful as a reference/cross-check, but runtime should prefer the project-maintained `data/ielts/part2/2026_may_august_topics.json`.

## Requirements

- Keep the top P2 corpus category entrances visible.
- Treat top category entrances as user-bound reusable material buckets, not current-season topic categories.
- Category entrance counts should reflect saved user material in that bucket, not the number of current-season cue cards.
- Add a current-season cue-card section below the categories.
- Cue cards should be based on the active question-bank scope, defaulting to the current season.
- Each cue card must include:
  - Stable `entry_id`.
  - `cue_id`.
  - Category and category label.
  - Title.
  - Bullets and rounding prompt.
  - `linked_question`.
  - Season/status metadata.
  - Existing saved `material_text`, if any.
  - Existing saved `p3_follow_up_text`, if any.
  - Official `p3_follow_ups` from the cue-card bank, if the bank provides them.
- Each cue card should expose two management actions:
  - `正文`: opens the existing P2 material editor for that cue card.
  - `P3 追问`: opens the existing P3 follow-up editor for that cue card.
- `P3 追问` should default-fill a Markdown scaffold from the cue card's official P3 follow-up questions, leaving blank answer slots for the learner to edit.
- `P3 追问` should provide a picker modal/list for selecting any number of official follow-up questions; do not assume the count is exactly five.
- Saving either entry point should update the same stable `P2CorpusEntry`, so existing material is not duplicated or lost.
- Retained questions must stay stable across seasons if the cue card text matches; old material should still attach through `linked_question` based stable IDs.

## Acceptance Criteria

- [x] `GET /api/p2-corpus` returns a `current_part2_cards` list for the active scope.
- [x] Each `current_part2_cards` item merges current question-bank cue-card metadata with any saved user corpus entry.
- [x] Existing `categories` payload remains backward compatible and exposes user-saved `material_count`.
- [x] Category entrance counts are not derived from current-season cue-card counts.
- [x] P2 corpus UI keeps category entrances at the top.
- [x] P2 corpus UI renders current-season cue cards below the category entrances.
- [x] Each cue card has separate `正文` and `P3 追问` actions.
- [x] `正文` opens the existing P2 material editor prefilled with saved material and cue-card metadata.
- [x] `P3 追问` opens the existing P3 follow-up editor prefilled with saved follow-up material.
- [x] `P3 追问` defaults to official cue-card P3 follow-up questions when no saved follow-up material exists.
- [x] `P3 追问` provides a selectable official-question picker and does not cap the question count at five.
- [x] Saving `正文` and `P3 追问` update the same stable entry, not two separate entries.
- [x] Existing saved entries remain visible/usable after the change.
- [x] Backend tests cover payload merge and stable save behavior.
- [x] Frontend syntax checks pass.

## Out of Scope

- Do not replace the speaking practice flow.
- Do not change report rendering.
- Do not import questionable PDF/question-bank sources into runtime.
- Do not delete archive/retained question data.
- Do not change P1 corpus behavior.
- Do not introduce AI generation for P2/P3 corpus in this task.

## Technical Notes

- Main backend file: `backend_django/apps/speaking/corpus_services.py`.
- Main frontend file: `web/static/corpus-takeaway.js`.
- Existing dialogs in `web/static/index.html` can likely be reused.
- Styling is likely in `web/static/styles.css` near P2 corpus selectors.
- Existing tests are in `backend_django/apps/speaking/tests.py`.
- Relevant data file: `data/ielts/part2/2026_may_august_topics.json`.
- Cross-check source snapshot: `.firecrawl/ieltsbro-api/ieltsbro-2026-5-8-catalog.json`.
