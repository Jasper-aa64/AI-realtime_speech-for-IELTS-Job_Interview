# Journal - JMaa32 (Part 1)

> AI development session journal
> Started: 2026-05-06

---



## Session 1: IELTS Speaking CLI Simulator P1/P2/P3 完整实现

**Date**: 2026-05-08
**Task**: IELTS Speaking CLI Simulator P1/P2/P3 完整实现
**Branch**: `main`

### Summary

补全 P1/P2/P3 CLI 模拟器：提升 CaptureAnswerOrFallback 为公共 API；P2 加 Enter 等待点；P3 接入 STT 和动态 claude 追问；修 shell 安全；新增 2026-spring 真题题库（6 P1 topic × 7 题 + 10 张 P2 cue card，来源 Cathoven/IELTSFever/IELTSLiz）

### Main Changes

- Added a compact per-turn `audio_preprocessing_metrics` summary for the feature-flagged speaking WASM observer.
- Persisted sanitized metrics on `SpeakingTurn.metadata` and exposed them through the runtime turn payload.
- Added regression coverage ensuring raw sample arrays are dropped and ratios are recomputed server-side.
- Captured the production diagnostics contract in `.trellis/spec/frontend/wasm-audio-guidelines.md`.

### Git Commits

| Hash | Message |
|------|---------|
| `bc74f0e` | (see git log) |
| `8780f16` | (see git log) |
| `e1e5841` | (see git log) |

### Testing

- [OK] `node --check web/static/app.js`
- [OK] `node --check web/static/wasm/speaking_audio_preprocessor.js`
- [OK] `python3 -m py_compile backend_django/apps/speaking/services.py backend_django/apps/speaking/tests.py`
- [OK] `.venv-django/bin/python backend_django/manage.py test apps.speaking.tests.SpeakingRuntimeApiTests.test_turn_complete_persists_audio_preprocessing_metrics -v 2`
- [OK] `.venv-django/bin/python backend_django/manage.py test apps.speaking.tests -v 1`
- [OK] `scripts/build_audio_core_wasm.sh`
- [OK] `git check-ignore -v web/static/wasm/audio_core_wasm.js web/static/wasm/audio_core_wasm.wasm`

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: 修复 stdin 缓冲区污染主菜单 bug

**Date**: 2026-05-08
**Task**: 修复 stdin 缓冲区污染主菜单 bug
**Branch**: `main`

### Summary

主菜单读取前加 tcflush(STDIN_FILENO, TCIFLUSH)，Part2Session::RecordSpeech 结束后同样 flush，防止多行粘贴残留换行污染主菜单循环导致 Unknown menu option 无限打印

### Main Changes

- Confirmed `backend_django/apps/ai/provider_adapters.py` already contains the planned Strategy / Template Method / Codex CLI Adapter / ProviderChain structure from `71ebbd9`.
- Verified public compatibility names remain exported from `apps.ai.provider_adapters`.
- Archived `.trellis/tasks/05-29-3` into the May 2026 task archive.

### Git Commits

| Hash | Message |
|------|---------|
| `22a20c9` | (see git log) |

### Testing

- [OK] `python3 -m py_compile backend_django/apps/ai/provider_adapters.py`
- [OK] `cd backend_django && ../.venv-django/bin/python manage.py test apps.ai -v 1`

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 3: Scorer 多后端 + codex exec 修 bug

**Date**: 2026-05-08
**Task**: Scorer 多后端 + codex exec 修 bug
**Branch**: `main`

### Summary

新增 ScorerBackend enum + ScorerConfig，支持 codex_exec（ChatGPT 账号）/ openai_api / claude 三后端；修 codex exec gpt-4o-mini 400 错误；修 temp 文件在 pclose 前被删导致 cat No such file 问题；config.json 新增 scorer 段。全链路验收通过：STT 识别英文、codex 评分返回真实 LLM feedback

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `fccc1af` | (see git log) |
| `a3ca973` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: IELTS UI wording and readability cleanup

**Date**: 2026-05-10
**Task**: IELTS UI wording and readability cleanup
**Branch**: `main`

### Summary

Improved IELTS Web UI readability, fixed China-facing explanation wording, clarified pronunciation estimate copy, and recorded spec conventions for natural Chinese guidance and dark-tone sidebar contrast.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `c0a810a` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 5: Implement IELTS docs 1.1-1.4

**Date**: 2026-05-10
**Task**: Implement IELTS docs 1.1-1.4
**Branch**: `main`

### Summary

Implemented IELTS China-facing scoring guidance, weak-question training persistence/replay APIs, local Codex usage billing ledger, UI settings surfaces, tests, and related code-spec contracts.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e1ab8ad` | (see git log) |
| `028eafc` | (see git log) |
| `d98b17e` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 6: Django migration backend stabilization

**Date**: 2026-05-15
**Task**: Django migration backend stabilization
**Branch**: `main`

### Summary

Built and stabilized the Django backend migration scaffold, AI task lifecycle, billing and provider runner boundaries, writing bridge contracts, and cleaned workspace blockers so the migration task could be archived.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e459018` | (see git log) |
| `706b424` | (see git log) |
| `1085b0e` | (see git log) |
| `ad0cd5b` | (see git log) |
| `f89bfb6` | (see git log) |
| `6edb061` | (see git log) |
| `d513ecc` | (see git log) |
| `4f3cd7e` | (see git log) |
| `c7aa533` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 7: Django writing frontend bridge milestone

**Date**: 2026-05-15
**Task**: Django writing frontend bridge milestone
**Branch**: `main`

### Summary

Implemented logged-in writing score-task bridge in the old Web UI, added old-origin AI task proxy coverage, documented frontend task polling contract, and verified old Web/Django/browser smoke checks.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 8: Finish Django writing frontend bridge

**Date**: 2026-05-15
**Task**: Finish Django writing frontend bridge
**Branch**: `main`

### Summary

Archived the Django writing frontend bridge after committing the old Web score-task bridge, proxy coverage, frontend spec update, tests, and browser verification.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `07a1acc` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 9: Django AI worker loop

**Date**: 2026-05-15
**Task**: Django AI worker loop
**Branch**: `main`

### Summary

Added a reusable Django AI task batch runner and continuous run_ai_worker command, covered writing-score loop, idle, stop-file, and stale-recovery behavior with tests, and documented the worker boundary.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `41f1e0e` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 10: Django writing reports history API

**Date**: 2026-05-15
**Task**: Django writing reports history API
**Branch**: `main`

### Summary

Add /api/writing/reports endpoint for writing reports page with owner-scoped entries, filters, and ai_task polling support. Decouple reports from monthly summary API.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `7f5f943` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 11: Optimize writing reports list hydration

**Date**: 2026-05-15
**Task**: Optimize writing reports list hydration
**Branch**: `main`

### Summary

Eliminate N+1 detail fetch on reports page. Store compact items, fetch detail only on selection. No cache, no backend changes.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `bd9bac5` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 12: Add Django speaking history DELETE API

**Date**: 2026-05-15
**Task**: Add Django speaking history DELETE API
**Branch**: `main`

### Summary

Add DELETE /api/history/{attempt_id} to complete speaking history API parity. Owner-scoped deletion with cascade. Frontend uses Django API.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `9abd7ed` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 13: Add Django speaking question bank training read APIs

**Date**: 2026-05-15
**Task**: Add Django speaking question bank training read APIs
**Branch**: `main`

### Summary

Migrate question bank and training observation read APIs. 4 endpoints with auth and owner scoping. Frontend paths unchanged.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `fb4931a` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 14: Design speaking session scoring audio migration

**Date**: 2026-05-15
**Task**: Design speaking session scoring audio migration
**Branch**: `main`

### Summary

Design document for migrating speaking practice flow from old server to Django. Phased plan with 6 phases. Risk matrix. No implementation.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `8ef60d4` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 15: Add Django attempts start endpoint

**Date**: 2026-05-16
**Task**: Add Django attempts start endpoint
**Branch**: `main`

### Summary

Implement POST /api/attempts/start for speaking practice sessions with all modes (mock, p1, p2, p3), creating SpeakingAttempt + SpeakingTurn records with response matching old server.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `bbfa834` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 16: Add Django speaking audio upload endpoint

**Date**: 2026-05-16
**Task**: Add Django speaking audio upload endpoint
**Branch**: `main`

### Summary

Design and implement Django POST /api/attempts/{id}/turns/{id}/audio and GET /api/audio/{id}/{id}/candidate with owner-scoped upload, validation, and retrieval.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `d984b0c` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 17: Add Django speaking runtime fallback endpoints

**Date**: 2026-05-16
**Task**: Add Django speaking runtime fallback endpoints
**Branch**: `main`

### Summary

Added Django fallback-only speaking runtime endpoints for turn completion, abort, and scoring; preserved old server for provider-heavy flows.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `0fdfd7a` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 18: Add feature-flagged Django speaking runtime proxy

**Date**: 2026-05-16
**Task**: Add feature-flagged Django speaking runtime proxy
**Branch**: `main`

### Summary

Added old-server feature flag and raw-body proxy support so migrated speaking runtime endpoints can route to Django while preserving fallback behavior.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `32b7c2c` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 19: Complete Django runtime migration

**Date**: 2026-05-16
**Task**: Complete Django runtime migration
**Branch**: `main`

### Summary

Complete Django runtime migration: add regenerate endpoints, mark old server deprecated, all 134 tests pass.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `b380a16` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 20: Finalize Django-only IELTS runtime cutover

**Date**: 2026-05-16
**Task**: Finalize Django-only IELTS runtime cutover
**Branch**: `main`

### Summary

Closed remaining Django-only runtime gaps: static frontend serving, fallback P3/TTS/latest-report contracts, frontend-compatible billing routes, tests, and cutover documentation.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `eee6725` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 21: Django runtime smoke verification

**Date**: 2026-05-16
**Task**: Django runtime smoke verification
**Branch**: `main`

### Summary

Add smoke tests for Django runtime verification covering auth, speaking, training, billing, writing. All 141 tests pass.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `83fddcc` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 22: Refine account settings and writing check-in layout

**Date**: 2026-05-16
**Task**: Refine account settings and writing check-in layout
**Branch**: `main`

### Summary

Separated account login/profile controls into a dedicated account page, restored Settings to wallet and weak training records, and stretched the writing check-in card with top calendar and bottom save/score controls.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `a33dc10` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 23: UI: Part 3 practice box spacing

**Date**: 2026-05-16
**Task**: UI: Part 3 practice box spacing
**Branch**: `main`

### Summary

Reduced padding and gap in p3-topic-panel, smaller font for mode help text

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `f482a85` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 24: Rebuild account auth experience

**Date**: 2026-05-16
**Task**: Rebuild account auth experience
**Branch**: `main`

### Summary

Migrated from toy account card to dedicated auth surfaces (login/register/forgot/profile/security). Hardened backend APIs: removed csrf_exempt, added CSRF endpoint, unified error structure, password validation, throttling. All tests pass (147/147).

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `7c797ee` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 25: Merge settings into account profile layout

**Date**: 2026-05-16
**Task**: Merge settings into account profile layout
**Branch**: `main`

### Summary

Removed standalone Settings UI, moved wallet, weak training, and replay queue into a two-column Account profile layout, and preserved account auth gating.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `cbd2764` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 26: Fix speaking audio upload CSRF

**Date**: 2026-05-16
**Task**: Fix speaking audio upload CSRF
**Branch**: `main`

### Summary

Diagnosed speaking practice Try Again failure as Django rejecting raw audio upload with missing CSRF token. Updated web/static/app.js finalizeTurn audio upload fetch to call ensureCsrfToken(), send X-CSRFToken when available, and keep same-origin credentials. Verified node syntax, speaking tests, full Django tests, system check, and migration dry-run.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 27: Add Writing Task1 image prompts and fix examiner TTS fallback

**Date**: 2026-05-16
**Task**: Add Writing Task1 image prompts and fix examiner TTS fallback
**Branch**: `main`

### Summary

Extended WritingPrompt with image_url and migration; rendered Task1 prompt images in writing surface with responsive fallback; made writing textarea auto-expand without inner scroll; fixed speaking examiner prompt fallback to browser TTS only when server audio_url is missing; full validation suite passed.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `6ef8976` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 28: Fix writing AI analysis regression after task1 image prompts

**Date**: 2026-05-16
**Task**: Add Writing Task1 image prompts and fix examiner TTS fallback
**Branch**: `main`

### Summary

Extended WritingPrompt with image_url and migration; rendered Task1 prompt images in writing surface with responsive fallback; made writing textarea auto-expand without inner scroll; fixed speaking examiner prompt fallback to browser TTS only when server audio_url is missing; full validation suite passed.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `6ef8976` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete

**Date**: 2026-05-16
**Task**: Fix writing AI analysis regression after task1 image prompts
**Branch**: `main`

### Summary

Fixed writing textarea infinite expansion that was squeezing AI score panel below viewport. Capped autoResizeWritingAnswer() at 800px max height and restored overflow-y auto. Preserved Task1 image rendering and all AI analysis/scoring functionality.

### Main Changes

- `web/static/styles.css`: Added max-height 800px to .writing-answer, changed overflow-y from hidden to auto
- `web/static/app.js`: Capped autoResizeWritingAnswer() target height at min(max(scrollHeight, 500), 800)

### Git Commits

| Hash | Message |
|------|---------|
| `9200651` | fix: cap writing textarea max height to prevent squeezing AI panel |

### Testing

- [OK] JS syntax check: passed
- [OK] Writing tests: 15/15 passed (3.493s)
- [OK] Full test suite: 147/147 passed (34.504s)
- [OK] Django system check: no issues
- [OK] Migrations check: no changes detected

### Status

[OK] **Completed**

### Next Steps

- None - regression fixed


## Session 29: Remove incorrect browser TTS fallback from speaking turns

**Date**: 2026-05-16
**Task**: Remove incorrect browser TTS fallback from speaking turns
**Branch**: `main`

### Summary

Removed browser speechSynthesis fallback mistakenly added in 6ef8976. Backend audio_url: None is normal pending state, not failure - AI worker generates audio asynchronously. Restored original behavior: only show server audio when audio_url exists.

### Main Changes

- `web/static/app.js`: Restored renderExaminerAudio() to 6ef8976^ logic, removed browser TTS else-if branch

### Git Commits

| Hash | Message |
|------|---------|
| `529cb0a` | fix: remove incorrect browser TTS fallback from speaking turns |

### Testing

- [OK] JS syntax check: passed
- [OK] Full test suite: 147/147 passed (28.359s)

### Status

[OK] **Completed**

### Next Steps

- None - TTS logic restored to original


## Session 30: Restore server-side examiner TTS in Django runtime

**Date**: 2026-05-16
**Task**: Restore server-side examiner TTS in Django runtime
**Branch**: `main`

### Summary

Migrated volcengine_tts() and ensure_examiner_tts() from legacy server to Django. Modified start_attempt() to generate examiner TTS for all turns after creation and store in turn metadata. TTS audio files cached in media/tts/examiner/ with deterministic cache keys. Environment variable IELTS_WEB_DISABLE_VOLCENGINE_TTS=1 disables generation for testing.

### Main Changes

- `backend_django/apps/speaking/services.py`: 
  * Added volcengine_tts() function with VolcEngine API call, caching, and fallback logic
  * Added ensure_examiner_tts() to generate TTS for turn examiner text
  * Modified start_attempt() to call ensure_examiner_tts() for all turns and save to metadata
  * Added _safe_slug() helper for filename sanitization
  * Added imports: base64, os, re, urllib.error, urllib.request

### Git Commits

| Hash | Message |
|------|---------|
| `e93a181` | feat: restore server-side examiner TTS in Django runtime |

### Testing

- [OK] JS syntax check: passed
- [OK] Speaking tests: 61/61 passed (59.552s)
- [OK] Full test suite: 147/147 passed (61.104s)
- [OK] Django system check: no issues

### Status

[OK] **Completed**

### Next Steps

- None - server-side TTS fully restored


## Session 28: Fix Django speaking Codex prompt delivery

**Date**: 2026-05-16
**Task**: Fix Django speaking Codex prompt delivery
**Branch**: `main`

### Summary

Fixed root cause: run_codex missing stdin flag, migrated 16 helper functions from old server, updated coaching prompt to full 50-line version

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `87a27bb` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 29: Migrate complete build_turn_feedback logic

**Date**: 2026-05-16
**Task**: Migrate complete build_turn_feedback logic
**Branch**: `main`

### Summary

Fixed Django feedback generation: added feedback_generation_status/backend/error fields, target_band fields, complete P1 answer generator, build_turn_feedback unified function, proper report payload sync

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `a4ec4a2` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 30: Complete Django speaking migration from old server

**Date**: 2026-05-16
**Task**: Complete Django speaking migration from old server
**Branch**: `main`

### Summary

Migrated all missing scoring/calibration functions: calibrate_realistic_score, heuristic_score, band_cap, development_markers, generic_template_score, simple_grammar_ratio, is_template_like_answer, append_calibration_note, prompt_relevance, cap_off_topic_score, score_prompt_for_part, turn_habit_tags, part_focus_text, infer_primary_focus, overall_review_with_codex, build_overall_review, build_personalized_coaching, attempt_part, target_band, score_for_part, build_part_scores, band_advice-based _criteria_feedback. All 147 tests pass.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `4cad49d` | (see git log) |
| `ea7b415` | (see git log) |
| `acf05da` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 31: Fix Codex JSON parsing with Trellis injection

**Date**: 2026-05-16
**Task**: Fix Codex JSON parsing with Trellis injection
**Branch**: `main`

### Summary

Fixed root cause: extract_json_object() greedy regex failed when Trellis injection text appeared before JSON. Implemented balanced bracket scanning and proper agent_message extraction from Codex events.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `742bd62` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 32: Fix speaking AI feedback fallback policy

**Date**: 2026-05-17
**Task**: Fix speaking AI feedback fallback policy
**Branch**: `main`

### Summary

Relaxed Speaking AI feedback validation so Codex owns Band 7 rewrites and coaching structure, removed brittle question-aware/vocabulary heuristics and hardcoded Band 7 fallbacks, added Codex-backed P1 work-study follow-up generation, documented the policy, regenerated bad attempt 0ed733ee0e6e46a2931796c3fdb422af, and verified tests.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 33: Add corpus and language takeaway flow

**Date**: 2026-05-18
**Task**: Add corpus and language takeaway flow
**Branch**: `main`

### Summary

Implemented corpus management, Language Takeaway translation and vocabulary book UI.

### Main Changes

Implemented P1/P2 corpus management and Language Takeaway flow.

Key changes:
- Added P1 corpus, P2 corpus, and Language Takeaway persistence in Django.
- Added Caiyun-compatible translation with local offline dictionary fallback.
- Added dedicated vocabulary book UI with compact two-column cards, optional hidden-Chinese study mode, and click-to-speak interaction.
- Added old web server proxy coverage for corpus and takeaway APIs.
- Added migrations, admin registration, API tests, and old server proxy regression tests.

Validation:
- node --check web/static/app.js
- python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py
- backend_django/manage.py check
- backend_django/manage.py makemigrations --check --dry-run
- backend_django/manage.py test apps.speaking.tests -v 1


### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 34: Redesign home and corpus library views

**Date**: 2026-05-18
**Task**: Redesign home and corpus library views
**Branch**: `main`

### Summary

Added a real Home view as the default entry point, moved practice runtime out of the landing screen, redesigned Home/Corpus/Language Takeaway views with consistent card styling, and added an icon-based hide/show Chinese control.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 35: Fix Language Takeaway source enter behavior

**Date**: 2026-05-18
**Task**: Fix Language Takeaway source enter behavior
**Branch**: `main`

### Summary

Changed the Language Takeaway popup so Enter in the source field re-runs translation, while Shift+Enter preserves multiline editing. Shared initial popup translation and manual retranslation through one helper.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 36: Allow public tunnel CSRF trusted origins

**Date**: 2026-05-18
**Task**: Allow public tunnel CSRF trusted origins
**Branch**: `main`

### Summary

Added DJANGO_CSRF_TRUSTED_ORIGINS support, restarted the local Django server with the active trycloudflare origin, and verified public login POST now reaches the login view instead of failing CSRF origin checks.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 37: Enlarge Language Takeaway popup typography

**Date**: 2026-05-18
**Task**: Enlarge Language Takeaway popup typography
**Branch**: `main`

### Summary

Increased the Language Takeaway popup source/Chinese label and textarea font sizes, with larger padding and textarea height for readability.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 38: Fix corpus subpage back navigation

**Date**: 2026-05-18
**Task**: Fix corpus subpage back navigation
**Branch**: `main`

### Summary

Changed the corpus subpage top-left back button label from 返回练习 to 返回 and made P1 corpus, P2 corpus, and takeaway book return to the corpus landing page.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 39: Fix corpus navigation from locked practice

**Date**: 2026-05-18
**Task**: Fix corpus navigation from locked practice
**Branch**: `main`

### Summary

Allowed corpus navigation while a practice session is locked by exiting/aborting through the existing cleanup path before switching to corpus, while keeping practice-mode switching locked.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 40: Prevent initial home flash for direct corpus views

**Date**: 2026-05-18
**Task**: Prevent initial home flash for direct corpus views
**Branch**: `main`

### Summary

Added an app booting state so the workspace stays hidden until URL-driven initial view selection applies, preventing direct corpus views from flashing the default home page first.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 41: Prevent sidebar and theme boot jitter

**Date**: 2026-05-18
**Task**: Prevent sidebar and theme boot jitter
**Branch**: `main`

### Summary

Hid the entire shell during app boot and applied stored typeface immediately during initialization so refresh/direct URL loads no longer flash 首页/default theme before the requested view and theme settle.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 42: Improve perceived latency for reports and takeaways

**Date**: 2026-05-18
**Task**: Improve perceived latency for reports and takeaways
**Branch**: `main`

### Summary

Added session-level stale-then-refresh caches for language takeaways, speaking history list/detail, and writing report list/detail so revisits and repeated report switching render immediately while background refresh preserves freshness.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 43: Prefetch reports and takeaways after login

**Date**: 2026-05-18
**Task**: Prefetch reports and takeaways after login
**Branch**: `main`

### Summary

Added idle authenticated prefetch for language takeaways, speaking history, and writing reports so first report/book clicks can use warmed frontend caches; updated static asset version and cleared user-scoped caches on logout.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `4d8a86a` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 44: Fix language takeaway popup sizing and viewport bounds

**Date**: 2026-05-18
**Task**: Fix language takeaway popup sizing and viewport bounds
**Branch**: `main`

### Summary

Reduced Language Takeaway popup textarea type size, added viewport-clamped popup placement for opening and dragging, and bumped static asset version so browsers load the fix.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e91684f` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 45: Responsive density and bounded selection trigger

**Date**: 2026-05-18
**Task**: Responsive density and bounded selection trigger
**Branch**: `main`

### Summary

Added compact desktop density rules for laptop-sized viewports, made the Language Takeaway selection trigger circular, delayed trigger display until selection completion, clamped trigger placement inside the viewport, and bumped static assets.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `9b1744a` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 46: Conceal English in takeaway review mode

**Date**: 2026-05-18
**Task**: Conceal English in takeaway review mode
**Branch**: `main`

### Summary

Changed Language Takeaway self-test mode to conceal English source text while keeping Chinese visible, updated toggle copy, preserved card dimensions, and bumped static asset version.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `15457d2` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 47: Rename Takeaway book label

**Date**: 2026-05-18
**Task**: Rename Takeaway book label
**Branch**: `main`

### Summary

Renamed learner-facing 生词本 labels to Takeaway across sidebar, corpus card, page heading, popup action, auth copy, and loading copy while preserving existing route/API names.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `d8d5507` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 48: Compact practice layout for Windows Edge

**Date**: 2026-05-18
**Task**: Compact practice layout for Windows Edge
**Branch**: `main`

### Summary

Added compact desktop practice sizing for laptop browsers: smaller practice title/subtitle, status area, prompt cards, recorder panes, timer, recording control, icon, and labels; bumped static asset version.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `7c4be25` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 49: Restructure writing reports and enforce paragraphs

**Date**: 2026-05-19
**Task**: Restructure writing reports and enforce paragraphs
**Branch**: `main`

### Summary

Added paragraph validation before writing AI scoring, reworked writing report detail into prompt/overall/paragraph review groups, added structure-advice-only handling for messy essays, and added frontend modal guidance plus tests.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `f039938` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 50: Require AI-supplied writing paragraph analysis

**Date**: 2026-05-19
**Task**: Require AI-supplied writing paragraph analysis
**Branch**: `main`

### Summary

Corrected writing report analysis so successful AI scores must provide their own structured overall review, practice focus, paragraph reviews, or structure-advice-only payload. Removed local hard-coded paragraph/model-answer generation from the AI path and kept fallback explicitly marked.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `079e7d8` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 51: Wire Codex writing report generation

**Date**: 2026-05-19
**Task**: Wire Codex writing report generation
**Branch**: `main`

### Summary

Connected writing score worker to a real Codex adapter, requiring JSON output with IELTS scores, overall review, practice focus, model answer, and paragraph reviews. Invalid Codex output now falls back explicitly instead of displaying fake AI report content.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `205f698` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 52: Record WASM speaking preprocessing metrics

**Date**: 2026-05-30
**Task**: Record WASM speaking preprocessing metrics
**Branch**: `main`

### Summary

Added feature-flagged per-turn WASM audio preprocessing diagnostics, server-side sanitization/persistence, tests, and WASM audio spec guidance.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `09050d9` | (see git log) |
| `e96e355` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 53: Archive apps.ai provider adapter refactor

**Date**: 2026-05-30
**Task**: Archive apps.ai provider adapter refactor
**Branch**: `main`

### Summary

Verified apps.ai provider adapter refactor, confirmed apps.ai tests pass, and archived the implementation task.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `71ebbd9` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
