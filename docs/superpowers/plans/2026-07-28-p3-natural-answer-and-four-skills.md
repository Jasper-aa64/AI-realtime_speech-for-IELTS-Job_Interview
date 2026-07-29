# P3 Natural Answer And Four Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Share one natural Band 7.5+ P3 answer contract across every generation path and render four P3 discussion-skill cards in a stable 2x2 grid.

**Architecture:** Put the answer contract in `coaching_services.py`, where the existing part-specific model-answer constraints live, and inject it into every full and compact prompt in `services.py`. Remove the fifth skill at the backend source and defensively filter legacy payloads in `app.js`; make the CSS grid explicit.

**Tech Stack:** Django/Python prompt services and tests, vanilla JavaScript report renderer, CSS Grid, Node source-contract tests.

## Global Constraints

- Do not change the selected target-band label or scoring calculations.
- Keep `band7_version` TTS-safe: spoken English answer only.
- Do not invent specific learner facts merely to satisfy the personal-lens rule.
- Do not restart Django, the AI worker, or cloudflared for these code changes.
- Preserve unrelated dirty-worktree changes.

---

### Task 1: Shared P3 model-answer contract

**Files:**
- Modify: `backend_django/apps/speaking/coaching_services.py`
- Modify: `backend_django/apps/speaking/services.py`
- Test: `backend_django/apps/speaking/tests.py`

**Interfaces:**
- Produces: `p3_model_answer_constraints() -> str`
- Consumes: `model_answer_constraints(part: str) -> str`

- [ ] **Step 1: Write failing prompt-contract tests**

Add tests that capture the prompts from `build_turn_band7_with_codex`,
`turn_feedback_with_codex`, and `turn_feedback_batch_with_codex`. Assert that
each P3 path contains the 45-70 second range, natural-conversation rule,
China-context/personal-lens guidance, diplomatic qualification, non-mechanical
active listening, and answer-only/TTS-safe rule.

- [ ] **Step 2: Run focused tests and verify RED**

Run:
`py backend_django/manage.py test apps.speaking.tests.SpeakingServiceTests.test_p3_model_answer_contract_is_shared`

Expected: failure because the shared contract and required clauses are absent.

- [ ] **Step 3: Implement the shared contract**

Add `p3_model_answer_constraints()` in `coaching_services.py`; make
`model_answer_constraints("p3")` return it. Replace the duplicate P3 text in
`build_turn_band7_with_codex`, add the constraint to the compact single-turn
retry, and inject per-part model constraints into the batch prompt.

- [ ] **Step 4: Run focused prompt tests and verify GREEN**

Run the new P3 prompt tests and the existing P2 prompt tests to prove the P2
contract did not change.

### Task 2: Four-dimension P3 skills payload

**Files:**
- Modify: `backend_django/apps/speaking/services.py`
- Test: `backend_django/apps/speaking/tests.py`

**Interfaces:**
- Produces: `p3_discussion_skills.dimensions` with exactly four stable keys
- Consumes: AI enrichment keyed only by dimensions supplied from the heuristic

- [ ] **Step 1: Write failing four-dimension tests**

Assert that `build_p3_discussion_skills()` returns exactly
`abstract_extension`, `reasoning`, `comparison_concession`, and
`specific_support`; assert the score/enrichment prompt omits
`follow_up_handling`.

- [ ] **Step 2: Run focused tests and verify RED**

Run the three existing `test_p3_discussion_skills_*` tests plus the new key-set
test. Expected: the key-set test finds the legacy fifth dimension.

- [ ] **Step 3: Remove the fifth dimension**

Delete the `follow_up_handling` heuristic entry and remove references to
追问承接 from the summary/prompt guidance. Keep follow-up turns available as
evidence for the remaining four dimensions, but do not expose a fifth card.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run all P3 discussion-skills tests and confirm AI status preservation still
works for the four supplied keys.

### Task 3: Legacy-safe 2x2 report layout

**Files:**
- Modify: `web/static/app.js`
- Modify: `web/static/styles.css`
- Modify: `web/static/index.html`
- Create: `tests/p3-discussion-skills-four-grid.test.js`

**Interfaces:**
- Consumes: current or legacy `skills.dimensions`
- Produces: four visible cards, two columns on normal widths, one column on narrow mobile

- [ ] **Step 1: Write failing frontend contract test**

Assert that the renderer filters `follow_up_handling`, limits the supported key
set to four, and CSS uses `repeat(2, minmax(0, 1fr))`.

- [ ] **Step 2: Run the Node test and verify RED**

Run: `node tests/p3-discussion-skills-four-grid.test.js`

Expected: failure because the renderer maps every saved dimension and CSS uses
`auto-fit`.

- [ ] **Step 3: Implement filtering and grid**

Filter dimensions through the four-key allowlist before rendering. Replace the
desktop `auto-fit` grid with two explicit equal columns and add a one-column
rule inside the existing narrow responsive block. Bump the relevant
`app.js`/CSS cache query values in `index.html`.

- [ ] **Step 4: Run frontend verification**

Run the new test, `node --check web/static/app.js`, and report-related Node
tests.

### Task 4: Integrated verification

**Files:**
- Verify only the files changed above

- [ ] **Step 1: Run backend checks**

Run focused speaking prompt/skills tests, then `py backend_django/manage.py check`.

- [ ] **Step 2: Run frontend checks**

Run the new Node test, `node --check web/static/app.js`, and relevant report UI
tests.

- [ ] **Step 3: Check patch hygiene**

Run:
`git diff --check -- backend_django/apps/speaking/coaching_services.py backend_django/apps/speaking/services.py backend_django/apps/speaking/tests.py web/static/app.js web/static/styles.css web/static/index.html tests/p3-discussion-skills-four-grid.test.js`
