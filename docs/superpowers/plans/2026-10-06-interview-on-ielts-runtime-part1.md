# Interview on the IELTS runtime — Part 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Interview practice and reports run on the real IELTS speaking components (examiner reads → 3 s prepare → auto-record → server ASR → report rail with menu/delete), the interview home is the IELTS `#homePanel` itself, and the top-right avatar card morphs out of the avatar like the top-left switcher.

**Architecture:** Interview sessions become `SpeakingAttempt` modes `iv_full` / `iv_project` / `iv_knowledge` / `iv_reverse`. `apps.interview.engine` supplies the question plan, the next/follow-up/probe decision (run inside `complete_turn`) and the 100-point score (run inside `/score`, synchronous). The frontend adds four practice views with the same names to `app.js`, so `startPractice`, `playExaminerTurn`, `beginPreparation`, `startRecording`, `complete`, `scoreAttempt`, `loadHistory` and `renderDetail` are the IELTS code paths; interview-specific bits are small branches keyed on `isInterviewView()` / `isInterviewMode(mode)`.

**Tech Stack:** Django 5 (apps.speaking, apps.interview), vanilla JS (`web/static/app.js`, `interview.js`, `home-dashboard.js`), QtWebEngine desktop shell for verification (CDP on `QTWEBENGINE_REMOTE_DEBUGGING`).

**Spec:** `docs/superpowers/specs/2026-10-06-interview-on-ielts-runtime-design.md`

## Global Constraints

- Never commit `backend_django/db.sqlite3`; never commit `.trellis/workspace/codex/`. Branch `ui-polish`, local only.
- UI copy that IELTS shows stays exactly as IELTS (e.g. record button "Start / Record the full section. No typing."). Interview-only copy is Chinese.
- Interview examiner speaks Chinese; no typed answers anywhere in the interview flow; an empty transcript is handled like IELTS (saved as empty, follow-up skipped).
- Depth limits (server-enforced): standard 1 follow-up per question; pressure 3 (project 4); reverse stage never follow-ups.
- Answer limits (seconds): self_intro 120, project 180, knowledge 120, follow-up 90, reverse 60; prepare 3 for all.
- Every new style for IELTS-equivalent UI must come from the IELTS rules (aliases or the real element), not hand-written lookalikes.
- After each task: `node --test tests/*.test.js` and `.venv-django/bin/python backend_django/manage.py test apps.interview apps.speaking` (12 pre-existing unrelated failures in the full suite are known; the two named apps must not gain failures). Bump the asset version string `20261006-interview-NN` in `web/static/index.html` (and tests that pin it) whenever `web/static/*.js|css` changes.
- Visual check after UI tasks in a visible Qt window: `QTWEBENGINE_REMOTE_DEBUGGING=9334 "build-desktop/IELTS Studio.app/Contents/MacOS/IELTS Studio" --server http://127.0.0.1:8767/` (user's own DB) and compare with the IELTS counterpart screenshot.

---

### Task 1: Top-left switcher — drop the key-hint footer, lighter dark card

**Files:**
- Modify: `web/static/index.html` (line with `class="studio-switch-foot"`)
- Modify: `web/static/styles.css` (`--switch-bg` for the dark tone, ~line 46282)

- [ ] **Step 1:** Delete the line `<div class="studio-switch-foot" aria-hidden="true">…</div>` from `index.html`, and delete every `.studio-switch-foot` rule in `styles.css` (`grep -n studio-switch-foot web/static/styles.css`).
- [ ] **Step 2:** In the dark-tone token block change
  `--switch-bg: color-mix(in srgb, var(--switch-surface) 55%, #000);` →
  `--switch-bg: color-mix(in srgb, var(--switch-surface) 88%, #fff);`
  (lighter than the rail instead of darker; light tone unchanged).
- [ ] **Step 3:** Bump asset version, run web tests, open the switcher in dark mode in the visible window and screenshot; the card must read clearly against the rail.
- [ ] **Step 4:** Commit `feat(web): lighter dark switcher card, no key-hint footer`.

### Task 2: Shared corner-morph helper; avatar card morphs out of the avatar; appearance styles move into it

**Files:**
- Create: `web/static/corner-morph.js` (loaded before `interview.js` and `app.js`)
- Modify: `web/static/interview.js` (switcher uses the helper), `web/static/app.js` (`setupQuickSettings`, font-style buttons), `web/static/index.html` (move `.font-tool` into `#quickSettingsCard`), `web/static/styles.css`
- Test: `tests/corner-morph.test.js`

**Interfaces:**
- Produces: `window.IELTSCornerMorph.create({ trigger, card, body, anchor: "top-left" | "top-right", palette: () => void, onOpenChange?: (open) => void })` → `{ open(): void, close(): void, toggle(): void, isOpen(): boolean }`. Handles hover intent (90 ms open / 240 ms close for mouse), click toggle, Esc, outside pointerdown, resize, reduced motion, the 500/380 ms spring (`SPRING` linear() string moved here from `interview.js`) and the 200/100 ms blur cross-fade of `body`.

- [ ] **Step 1: Failing test** — `tests/corner-morph.test.js` loads `corner-morph.js` in `vm` with a fake DOM (same harness style as `tests/interview-ui.test.js`) and asserts: `create(...).open()` positions the card at the trigger's top-left for `anchor:"top-left"` and at `right = innerWidth - rect.right` for `anchor:"top-right"`; `close()` sets `hidden` after the animation's `finished` resolves; a second `open()` while closing cancels the close.
- [ ] **Step 2:** Run `node --test tests/corner-morph.test.js` → FAIL (module missing).
- [ ] **Step 3:** Implement `corner-morph.js` by moving `reducedMotion`, `animateMenu` and `menu` logic out of `interview.js` (lines ~93–160) and parameterising the anchor: for `top-right` set `card.style.right = ${innerWidth - from.right}px; card.style.left = "auto"` instead of `left`. Keyframes stay `{width,height,borderRadius 10→18,background,border,shadow}`.
- [ ] **Step 4:** `interview.js` switcher: replace its own `menu/animateMenu/hover` code with `IELTSCornerMorph.create({ trigger: #studioModeTrigger, card: #studioModeMenu, body: .studio-switch-body, anchor: "top-left", palette: syncSwitchPalette })`; keep keyboard navigation and `changeMode`.
- [ ] **Step 5:** Avatar card: in `index.html` move the `.font-tool` block (APPEARANCE label + 3 `.font-option` buttons) from the sidebar bottom into `#quickSettingsCard` after the 外观 segment, under a `<p class="quick-settings-label">主题</p>`; remove the sidebar `.nav-divider` that preceded it. `#quickSettingsCard` gets an inner `.quick-settings-body` wrapper (cross-faded). In `setupQuickSettings` replace `show()` and the hover/focus listeners with `IELTSCornerMorph.create({ trigger: avatar, card, body: card.querySelector(".quick-settings-body"), anchor: "top-right", palette: syncQuickPalette, onOpenChange: (open) => { if (open) { sync(); toggleList(false); } } })`. The card's closed size equals the avatar circle (radius 999px → 18px open). The existing `[data-font-style]` click wiring keeps working (buttons moved, same attributes).
- [ ] **Step 6:** CSS: card `position: fixed; top: <avatar top>`; card surface tokens reuse `--switch-*` computed from the topbar background (light page → light tone). Remove `.font-tool` sidebar layout rules that assume the nav bottom; add compact `.quick-settings-card .font-options` sizing.
- [ ] **Step 7:** Tests pass; visible-window check: hover the avatar → card grows from the avatar's corner to the left/down; leave → shrinks back into the avatar; theme buttons work in the card; sidebar bottom no longer shows APPEARANCE.
- [ ] **Step 8:** Commit `feat(web): avatar card morphs from the avatar; appearance styles live in it`.

### Task 3: Interview home is the IELTS `#homePanel` with interview copy

**Files:**
- Modify: `web/static/index.html` (add `data-home-copy` keys to `#homePanel` text/link nodes), `web/static/interview.js` (home profile), `web/static/home-dashboard.js` (stats source switch), `web/static/app.js` (interview "home" nav → `switchView("home")`)
- Test: `tests/interview-home-profile.test.js`

**Interfaces:**
- Produces: `interview.applyHomeProfile(mode: "ielts" | "interview")` — swaps every `[data-home-copy]` node's text/href/`data-view`/`data-home-mode` from `HOME_COPY[mode][key]`, keeping the original IELTS values in a `WeakMap` so switching back restores them exactly. Called from `setProductMode` and after `switchView("home")`.

- [ ] **Step 1: Failing test** — build the `#homePanel` markup from `index.html` into a fake DOM, call `applyHomeProfile("interview")`, assert title-main reads `Mock Interview`, primary action links to `?view=iv_full`; call `applyHomeProfile("ielts")`, assert every node equals its original.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Annotate `#homePanel` nodes: `hx-kicker`, `hx-title-top`, `hx-title-main`, the four `hx-topics` spans, both `hx-actions` links, each slide's chip/strong/span and its link, the stat labels, the bank chips, the practice-path area cards and links. Interview copy (Chinese, from the current interview home): kicker `Interview Studio`; title-top `把做过的系统，讲成面试官想听的答案`; title-main `Mock Interview`; topics 项目 | 知识点 | 语料 | 报告; actions 开始完整面试 → `iv_full`, 更新简历 / JD → `ivCustom`; slides reuse the current five images as placeholders with interview captions (完整面试 / 项目讲述 / 知识点 / 百分制报告 / 简历题卡); stats 面试场次 / 平均分 / 最近练习; areas 面试练习 / 面试语料 / 面试报告.
- [ ] **Step 4:** `home-dashboard.js` `refreshStats`: when `document.body.classList.contains("interview-mode")`, read `/api/history?domain=interview` (count, average of `interview_total`, last time) instead of speaking/writing totals; bank chips show corpus counts from `/api/interview/corpus/`.
- [ ] **Step 5:** Interview nav item 面试首页 → `switchView("home")`; delete the interview `home()` renderer, `SLIDES`, `showSlide`, and the `#interviewHome` alias entry in `scripts/alias_ielts_styles.py` plus its generated selectors (re-run the script after removing the entry is not enough — remove `#interviewHome` selectors with a one-off `sed`/python pass and confirm `grep -c interviewHome styles.css` is 0).
- [ ] **Step 6:** Tests pass; visible window: IELTS home and interview home screenshots overlap pixel-for-pixel apart from text/images.
- [ ] **Step 7:** Commit `feat(web): interview home is the IELTS home panel with interview copy`.

### Task 4: Backend — interview speaking modes and turns

**Files:**
- Modify: `backend_django/apps/speaking/models.py` (`SpeakingAttempt.Mode` choices), new migration
- Modify: `backend_django/apps/speaking/services.py` (`start_attempt`, `_build_turns`)
- Create: `backend_django/apps/interview/runtime.py` (bridge between speaking and interview engine)
- Modify: `backend_django/apps/speaking/tts_services.py`, `examiner_tts_services.py` (language/voice)
- Test: `backend_django/apps/interview/tests_runtime.py`

**Interfaces:**
- Produces: `apps.interview.runtime.INTERVIEW_MODES = {"iv_full": "full", "iv_project": "project", "iv_knowledge": "knowledge", "iv_reverse": "reverse"}`; `is_interview_mode(mode: str) -> bool`; `build_turns(user, mode, payload) -> tuple[str, str, list[dict], None, dict]` (same tuple shape as `_build_turns`); `ANSWER_SECONDS = {"self_intro": 120, "project": 180, "knowledge": 120, "award": 120, "reverse": 60, "follow_up": 90}`.
- Turn dict shape (consumed by `start_attempt` and the frontend): `{"id", "part": "interview", "question", "examiner_text", "prompt": {"role": "main", "stage", "corpus_entry_id", "question_id", "language": "zh", "depth": 0}, "timers": {"prep_seconds": 3, "speak_seconds": ANSWER_SECONDS[stage]}, "display_index", "counts_toward_total": True}`.

- [ ] **Step 1: Failing tests** in `tests_runtime.py`:
  - `POST /api/attempts/start {"mode": "iv_full"}` without resume → 400 with the Chinese `resume_required` message.
  - With seeded resume entries (reuse `seed_resume` from `tests_engine.py`) → 200; `mode == "iv_full"`; turn stages `self_intro, project, project, knowledge×5, award, reverse`; every turn `part == "interview"`, `timers.prep_seconds == 3`, project `speak_seconds == 180`; `prompt.language == "zh"`.
  - `iv_knowledge` with `count: 3, category: "cpp"` → 3 knowledge turns.
  - `examiner_tts` requested with `language="zh"` (patch `apps.speaking.tts_services.volcengine_tts` and assert the call kwargs).
- [ ] **Step 2:** Run `manage.py test apps.interview.tests_runtime` → FAIL.
- [ ] **Step 3:** Add the four choices to `SpeakingAttempt.Mode`, `makemigrations speaking`. In `start_attempt` accept `mode in {"p1","p2","p3","mock"} | INTERVIEW_MODES`; in `_build_turns` first line `if is_interview_mode(mode): return interview_runtime.build_turns(payload.get("_user"), mode, payload)`; map `InterviewError` to `ValueError` with the same message so the existing view returns 400. `runtime.build_turns` calls `engine.build_plan(user, {"part": INTERVIEW_MODES[mode], "intensity": payload.get("iv_intensity","standard"), "count": …, "category": …, "project_ids": …})` and converts each plan item into the turn dict above (ids `iv-<n>`); attempt metadata `{"interview": {"part", "intensity", "plan_stages"}}`; title = `PART_TITLES[part]`.
- [ ] **Step 4:** TTS language: `volcengine_tts(..., language="en")` parameter (default unchanged); `ensure_examiner_tts` passes `language="zh", voice=settings.INTERVIEW_EXAMINER_VOICE` when `turn["prompt"].get("language") == "zh"` (cache key includes the language). Probe the translate TTS endpoint once with `language="zh"` and candidate speakers (`zh_male_rap`, `zh_female_qingxin`, `zh_male_yunzhou_jupiter_bigtts`); set the default `INTERVIEW_EXAMINER_VOICE` to the first that returns audio and record the result in the handoff doc.
- [ ] **Step 5:** Tests pass; `manage.py test apps.speaking` unchanged.
- [ ] **Step 6:** Commit `feat(speaking): interview attempt modes built from the interview plan`.

### Task 5: Backend — the interviewer decides inside `complete_turn`

**Files:**
- Modify: `backend_django/apps/speaking/services.py` (`complete_turn`, after the transcript is saved and before `next_turn` is chosen)
- Modify: `backend_django/apps/interview/runtime.py` (`after_answer`)
- Test: `backend_django/apps/interview/tests_runtime.py`

**Interfaces:**
- Produces: `runtime.after_answer(user, attempt, turn, transcript: str, ai_source: str) -> dict` returning `{"inserted": SpeakingTurn | None, "skipped": {"message": str} | None}`; side effects: writes `turn.metadata["decision"]` and, for reverse, `turn.metadata["reply"]`.
- Rules: empty transcript → no AI call, `skipped = {"message": "没有检测到回答，已跳过追问。"}`; reverse stage → `reverse_reply` AI call, then insert a main reverse turn whose examiner text is `reply + "\n" + REVERSE_MORE` (only while reverse turns < `REVERSE_ROUNDS`); otherwise depth = count of follow_up ancestors (`prompt.parent_turn_id` chain); `depth >= depth_limit(intensity, stage)` → decision `next` (reason `depth_limit`), no AI call; else `next_step` AI call; `follow_up`/`probe` → insert a turn after this one with `prompt.role = "follow_up"`, `prompt.parent_turn_id`, `prompt.action`, `timers.speak_seconds = 90`, same stage, Chinese; AI failure → decision `failed`, move on. Inserted turns get examiner TTS via `ensure_examiner_tts` and later turns' `sequence` shift by one.

- [ ] **Step 1: Failing tests** (patch `apps.interview.runtime.ai_services.run_generation`):
  - standard: answer 1 (transcript patched via `transcribe_turn_audio_with_server_asr` or payload `transcript`) → `complete` response `next_turn.prompt.role == "follow_up"` with the AI text; answer the follow-up → no AI call, `next_turn` is the next project.
  - pressure: three consecutive probes allowed, fourth answer moves on (knowledge stage).
  - empty transcript → `follow_up_skipped.message` present, `run_generation` not called.
  - AI failure → next planned turn, decision status `failed`.
  - reverse: reply inserted as the next turn's examiner text; after `REVERSE_ROUNDS` the attempt has no next turn.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `after_answer` reusing `engine.depth_limit`, `STAGE_LABELS`, `REVERSE_MORE`, `REVERSE_ROUNDS` and the `inputs` construction from `engine.answer` (move that dict-building into a shared helper `engine.next_step_inputs(...)` used by both). In `complete_turn`, for `is_interview_mode(attempt.mode)` call it after the turn's transcript is saved; put `follow_up_skipped` into the response when `skipped`; the existing "next pending turn" lookup then naturally returns the inserted turn.
- [ ] **Step 4:** Tests pass.
- [ ] **Step 5:** Commit `feat(speaking): interview follow-ups decided when a turn completes`.

### Task 6: Backend — 100-point report and interview history

**Files:**
- Modify: `backend_django/apps/speaking/services.py` (`score_attempt`), `report_services.py` (`report_is_valid`, `history_item`, `history`), `views.py` (`history_view` reads `domain`)
- Modify: `backend_django/apps/interview/ai_schema.py` + prompt for `score_report` (add per-turn `reference_answer`)
- Modify: `backend_django/apps/interview/runtime.py` (`score`)
- Test: `backend_django/apps/interview/tests_runtime.py`

**Interfaces:**
- Produces: `runtime.score(user, attempt, ai_source) -> dict` (the report payload). Payload shape = IELTS report payload plus `interview_score = {"total", "dimensions": [{key,label,max,score,evidence}], "summary", "boundary", "next_steps", "limitations"}`; `ielts_score = None`; each payload turn has the IELTS fields the renderer reads (`id, part:"interview", question, prompt, transcript_raw, transcript_cleaned, display_transcript, audio, status:"completed"`) plus `band7_version`/`band7_markdown` = the AI reference answer and `ai_coaching` = Markdown of the interviewer's judgement (signal, evidence, boundary, per-turn comment, reverse reply).
- History item for interview: `{..., "mode": "iv_*", "interview_total": int | None, "overall_band": None}`.

- [ ] **Step 1: Failing tests:** finish an `iv_knowledge` attempt (1 turn), `POST /api/attempts/<id>/score` with `run_generation` patched to a valid `score_report` → 200, `interview_score.total` = sum, `turns[0].band7_version` = reference; `GET /api/history?domain=interview` lists it with `interview_total`; `GET /api/history` (default domain `ielts`) does not; aborted or zero-answer interview attempts are excluded; `DELETE /api/history/<id>` works unchanged.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** `ai_schema.validate("score_report")` accepts `per_turn[].reference_answer` (≤1500 chars, optional); prompt asks for a strong Chinese reference answer per answered turn. `runtime.score` builds inputs like `engine.score`, calls `run_generation`, writes `SpeakingReport(attempt, report_payload=…)` (band fields NULL) and sets `attempt.status = SCORED`. `score_attempt`: `if is_interview_mode(mode): return runtime.score(...)` before `create_speaking_report_task`. `report_is_valid`: interview modes are valid when status is SCORED and `report_payload.interview_score.total` is an int. `history(user, domain="ielts")` filters `mode__in` the domain's modes and drops interview attempts with no non-empty transcript. `history_view` passes `request.GET.get("domain", "ielts")`.
- [ ] **Step 4:** Tests pass (`apps.interview`, `apps.speaking`).
- [ ] **Step 5:** Commit `feat(speaking): 100-point interview reports in the speaking history`.

### Task 7: Frontend — interview practice views on the IELTS practice panel

**Files:**
- Modify: `web/static/app.js` (`PRACTICE_VIEWS`, `SPEAKING_PART_VIEWS`, `startPractice` payload, `syncP1IntensityPanel`, `turnProgressLabel`, `viewCopyFor`, corpus entry button, `loadHistory` domain)
- Modify: `web/static/index.html` (`#interviewNav` items become `data-view="iv_full|iv_project|iv_knowledge|iv_reverse|history|…"` links)
- Modify: `web/static/interview.js` (delete `practice()`, recorder, typing, `startRecording/stopRecording/submitAnswer`, the practice actions)
- Test: `tests/interview-practice-runtime.test.js`

**Interfaces:**
- Consumes: Task 4 turn shape, Task 5 `follow_up_skipped`.
- Produces: `isInterviewView(view)` (`view.startsWith("iv_")`), `INTERVIEW_STAGE_LABELS` (自我介绍/项目/知识点/奖项/反问).

- [ ] **Step 1: Failing test** (source-level + vm): `PRACTICE_VIEWS` contains the four iv views; `startPractice` sends `{mode: "iv_full", iv_intensity: state.p1Intensity === "high" ? "pressure" : "standard"}`; `turnProgressLabel({part:"interview", prompt:{stage:"project", role:"follow_up"}})` returns `项目 -> 追问`; `syncP1IntensityPanel` shows `#p1ModeSwitch` for iv views.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement: add views to both sets; `const mode = state.view === "mock" ? "mock" : state.view;` already yields `iv_*`; add `...(isInterviewView(mode) ? { iv_intensity: …, count, category, project_ids } : {})`; `syncP1IntensityPanel` uses `const isP1 = state.view === "p1" || isInterviewView(state.view)` (the switch markup, animation and pixel-flow stay IELTS); `turnProgressLabel` interview branch with stage labels; `viewCopyFor` entries for iv views (title = part name, subtitle = stage chain); the `#openP1CorpusBtn` label in interview views reads `我的面试语料库` and opens the interview corpus view (Part 2 replaces the target). Recording, examiner audio, prepare countdown and empty-answer handling are untouched IELTS code. Knowledge launch options (category/count) and project selection: reuse the P3 launch panel markup (`#p3TopicPanel` pattern) shown for `iv_knowledge` / `iv_project` before start.
- [ ] **Step 4:** Remove the interview practice code from `interview.js` and its CSS (`#interviewPractice*` aliases, `.iv-answer*`, `.iv-record*`).
- [ ] **Step 5:** Tests pass; visible window with the user's account: start 完整面试 → examiner audio plays (Chinese) → "Prepare … Recording starts in 3 seconds" → recording auto-starts → stop → next question; with ASR disabled the follow-up is skipped with the IELTS message; standard/pressure switch animates like P1.
- [ ] **Step 6:** Commit `feat(web): interview practice runs on the IELTS practice panel`.

### Task 8: Frontend — interview reports on the IELTS report rail and detail

**Files:**
- Modify: `web/static/app.js` (`loadHistory`, speaking report filter options, `renderHistoryList` tag/tone for iv modes, `renderDetail` interview branch, `turnTableSection` header text, score-complete modal)
- Modify: `web/static/interview.js` (delete `reportsPane` and helpers), `web/static/styles.css` (delete `#interviewReport*` aliases; add tone/tag rules for iv tags only if IELTS has no matching class — reuse `mock/p1/p2/p3` tones: iv_full→mock, iv_project→p2, iv_knowledge→p1, iv_reverse→p3)
- Test: `tests/interview-report-runtime.test.js`

**Interfaces:**
- Consumes: Task 6 payload (`interview_score`, `band7_version`, `ai_coaching`, `interview_total`).

- [ ] **Step 1: Failing test:** `renderDetail` with an interview payload renders `73 / 100`, five `.score-cell`s, a table with header `参考回答`, and no `Band`; `loadHistory` requests `/api/history?domain=interview` when `state.productMode === "interview"`; the filter menu lists 全部/完整面试/项目深挖/知识点/反问环节 in interview mode.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement in `renderDetail`: `if (isInterviewMode(attempt.mode))` build the summary card with the same classes as the IELTS card (section label `模拟面试 · 百分制估分`, band box `Overall 73 / 100`, `.score-row.compact.speaking-score-summary-grid` with five `scoreCell(label, score, "满分 " + max)`), `overallReviewSection` with summary/boundary/next steps as `review_points`, then `turnTableSection` (header text `参考回答` when interview). The 三个点 menu, delete, rail scroll and filter are untouched IELTS code. History list item band text for interview = `interview_total`.
- [ ] **Step 4:** Remove the interview report code and CSS.
- [ ] **Step 5:** Tests pass; visible window: reports rail identical to 口语报告 (menu ⋯ → delete works, no jitter on click), detail shows the 100-point card.
- [ ] **Step 6:** Commit `feat(web): interview reports use the IELTS report rail and detail`.

### Task 9: Verification and handoff

- [ ] Full run: web tests, `manage.py test apps.interview apps.speaking`, desktop `ctest` in `build-desktop`.
- [ ] End-to-end in the visible window on the user's server: 完整面试 start → finish → report → delete; switch to IELTS and run one P1 question to confirm nothing regressed.
- [ ] Update `docs/reports/qt-desktop-mock-interview-handoff-2026-10-05.md` (new section: what moved to the IELTS runtime, the voice chosen, what Part 2 covers) and commit.

## Part 2 (separate plan, after Part 1 is accepted)

Corpus screens (知识点 = P1 corpus, 简历 = P2 corpus + P3 follow-ups with unlimited items and the 全部/项目/技术栈/自我介绍/奖项 filter, JD 与反问 = P1 corpus), the report-opened editor with AI 参考, 简历/JD 定制 draft review before adding to the corpus, deleting the remaining `interview.js` panes and the old `/api/interview/sessions` endpoints.
