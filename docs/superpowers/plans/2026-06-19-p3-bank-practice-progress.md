# P3 Fixed-Bank Practice Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split fixed-bank P3 follow-ups into stable 3-4 question rounds and show report-backed completion progress on selectable P2 cards.

**Architecture:** The backend owns grouping, next-round choice, and completion derivation. Round identity is persisted in existing `SpeakingAttempt.metadata`; the frontend consumes progress fields and passes the selected plan through the existing P3 launch flow.

**Tech Stack:** Django 5 services/models/tests, vanilla JavaScript, CSS, Node test runner.

---

### Task 1: Pure round grouping and report-backed progress

**Files:**
- Modify: `backend_django/apps/speaking/corpus_services.py`
- Test: `backend_django/apps/speaking/tests.py`

- [ ] Write failing tests for 3, 4, 5, and 6-question grouping, including `[0,1,2]` plus `[3,4,2]` for five.
- [ ] Run the targeted Django tests and verify the grouping assertions fail.
- [ ] Add `p3_bank_practice_rounds()` and a bounded progress query that counts only `status=scored` attempts with `report__isnull=False`.
- [ ] Add deterministic next-round selection by `(completion_count, round_index)`.
- [ ] Run the targeted tests and verify they pass.

### Task 2: Persist round identity through P3 plan and attempt creation

**Files:**
- Modify: `backend_django/apps/speaking/services.py`
- Test: `backend_django/apps/speaking/tests.py`

- [ ] Write a failing API/service test asserting a five-question bank card returns only the chosen three-question round.
- [ ] Write a failing attempt test asserting metadata includes `p3_bank_cue_id`, `p3_bank_round_index`, `p3_bank_round_count`, and `p3_bank_followup_ids`.
- [ ] Run both tests and verify failure is caused by missing round selection/metadata.
- [ ] Apply the backend round selector before `_build_p3_turns()` and copy round metadata into the attempt metadata returned by `_build_turns()`.
- [ ] Run the targeted tests and verify they pass.

### Task 3: Expose progress in P2/P3 card payloads

**Files:**
- Modify: `backend_django/apps/speaking/corpus_services.py`
- Test: `backend_django/apps/speaking/tests.py`

- [ ] Write a failing test with started, aborted, report-less scored, and report-backed scored attempts.
- [ ] Assert only report-backed attempts populate `practice_completed_round_indexes` and `practice_is_complete`.
- [ ] Add one batched progress calculation in `p2_corpus_library()` and pass results into `p2_topic_card_payload()`.
- [ ] Run corpus payload tests and verify all pass without per-card database queries.

### Task 4: Render selectable partial/completed cards

**Files:**
- Modify: `web/static/app.js`
- Modify: `web/static/styles.css`
- Modify: `web/static/index.html`
- Create: `scripts/test_p3_bank_practice_progress.mjs`

- [ ] Write a failing Node regression test asserting partial/completed labels and CSS classes are emitted from progress fields.
- [ ] Run the Node test and verify it fails.
- [ ] Update `p3BankCardPreviewHtml()` to render `已练 1/2` and `已完成`, while preserving `tabindex=0`, `role=button`, and click behavior.
- [ ] Add restrained completed-card opacity, plus hover/focus restoration; do not set `pointer-events: none` or `disabled`.
- [ ] Invalidate/reload P2 corpus progress after a successful fixed-bank P3 report.
- [ ] Bump the `app.js` and stylesheet cache versions in `index.html`.
- [ ] Run the Node test and JavaScript syntax check.

### Task 5: Cross-layer verification

**Files:**
- Verify all files above.

- [ ] Run targeted P3 grouping/progress tests.
- [ ] Run `python backend_django/manage.py test apps.speaking`.
- [ ] Run `python backend_django/manage.py check`.
- [ ] Run `node --check web/static/app.js` and the Node regression test.
- [ ] Run `git diff --check` on touched files and inspect the final diff for unrelated changes.
