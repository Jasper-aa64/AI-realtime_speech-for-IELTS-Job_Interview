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

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `bc74f0e` | (see git log) |
| `8780f16` | (see git log) |
| `e1e5841` | (see git log) |

### Testing

- [OK] (Add test results)

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

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `22a20c9` | (see git log) |

### Testing

- [OK] (Add test results)

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
