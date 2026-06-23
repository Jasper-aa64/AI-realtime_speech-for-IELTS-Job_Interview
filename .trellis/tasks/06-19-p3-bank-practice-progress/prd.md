# P3 Fixed-Bank Practice Grouping and Completion State

## Goal

Turn each P2 card's fixed Part 3 follow-ups into stable 3-4 question practice rounds, and show durable progress on the card without preventing repeat practice.

## Requirements

- A card with 3-4 fixed follow-ups uses one round containing every question.
- A card with 5 fixed follow-ups uses two stable rounds: questions 1-3, then questions 4-5 plus question 3 as the bridge/repeated question.
- A card with 6 fixed follow-ups uses two stable rounds of 3 questions each.
- General grouping remains balanced at 3-4 questions per round for future cards with more questions.
- The backend is the single owner of grouping and round selection.
- Round completion counts only a scored P3 attempt with a persisted `SpeakingReport`.
- A two-round card shows `已练 1/2` after one distinct round and becomes completed only after both rounds have reports.
- Completed cards are visually dimmed but remain selectable; hover/focus restores clarity.
- Reopening a completed card selects the least-practised round, with deterministic round-index tie breaking.
- Existing reports and cards without round metadata remain valid and visible.

## Acceptance Criteria

- [ ] 3 and 4 follow-ups produce one round containing all questions.
- [ ] 5 follow-ups produce stable groups `[1,2,3]` and `[4,5,3]`.
- [ ] 6 follow-ups produce stable groups `[1,2,3]` and `[4,5,6]`.
- [ ] Starting a fixed-bank P3 attempt stores cue ID, round index/count, and selected follow-up IDs in attempt metadata.
- [ ] Aborted, started, ready-to-score, failed-report, and report-less attempts do not advance progress.
- [ ] A completed report advances progress and the picker renders `已练 1/2` or `已完成` appropriately.
- [ ] Completed cards remain keyboard- and pointer-selectable.
- [ ] Backend tests, frontend regression tests, JavaScript syntax check, and Django system check pass.

## Technical Approach

Add pure grouping and progress helpers in `corpus_services.py`. Reuse `SpeakingAttempt.metadata` as durable round identity and derive progress from scored attempts joined to `SpeakingReport`; no migration is needed. Include progress fields in current P2 card payloads. Pass the selected round through the existing P3 plan and start-attempt payload, then render progress classes and labels in the existing P3 bank picker.

## Decision (ADR-lite)

**Context:** Five questions cannot be split into two rounds while keeping both rounds at a minimum of three without one repeat.

**Decision:** Repeat question 3 in round two as a stable bridge. Persist round identity on the attempt and count only report-backed completions.

**Consequences:** The learner gets two viable three-question sessions and one intentional repeat. Progress is refresh-safe and cannot be advanced by merely opening or abandoning practice.

## Out of Scope

- AI-generated replacement questions for five-question cards.
- Changing P2 report/custom-theme P3 generation.
- New database tables or migrations.
- Hiding or disabling completed cards.

## Technical Notes

- Backend: `backend_django/apps/speaking/corpus_services.py`, `services.py`, `tests.py`.
- Frontend: `web/static/app.js`, `web/static/styles.css`, `web/static/index.html`.
- Current fixed-bank source is identified by `source` values `bank` / `season_bank` and `p2_question_id`.

