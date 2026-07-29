# Speaking Report Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make completed SpeakingAttempts visible and durable independently of AI report generation, with one backend-derived state shared by history/detail and a refresh-safe frontend.

**Architecture:** Add a persisted-data state resolver in `report_services.py`; history and detail serialize the resolver's state. Keep existing Attempt/Turn/Report/AITask tables and idempotent task creation. Update `app.js` to render explicit `unscored`, `scoring`, `failed`, and `ready` states and refresh from persisted task/detail data.

**Tech Stack:** Django ORM/TestCase, SQLite test DB, vanilla JavaScript, Node static assertions.

## Global Constraints

- Preserve existing user modifications and do not use destructive git commands.
- Do not start/retry AI tasks, worker services, cloudflared, or change the public URL.
- Do not alter or fabricate Band values.
- Backend persistence, not frontend memory, is the source of lifecycle truth.
- Use `apply_patch` for edits and run fresh verification before claiming completion.

### Task 1: Backend lifecycle contract (RED → GREEN)

**Files:**
- Modify: `backend_django/apps/speaking/report_services.py`
- Test: `backend_django/apps/speaking/tests.py`

- [ ] Add failing tests for reportless completed Attempts, old no-task Attempts, pending/running, 403 balance error, success/failure parity, and deletion isolation.
- [ ] Run the focused Django tests and confirm failure is caused by reportless history/detail filtering.
- [ ] Implement one resolver and shared serializers; add explicit `unscored` payloads and normalize provider errors.
- [ ] Re-run the focused tests, including the real-data-shaped Attempt ID without inserting duplicate production data.

### Task 2: Task boundary safety

**Files:**
- Modify: `backend_django/apps/speaking/services.py`
- Modify: `backend_django/apps/speaking/views.py` only if error mapping requires it
- Test: `backend_django/apps/speaking/tests.py`

- [ ] Add failing coverage that an active task reuses the same Attempt and a terminal retry creates no duplicate Attempt/report card.
- [ ] Verify the score/retry path continues to preserve turns/audio/transcript and persists queue/failure transitions.
- [ ] Make only the minimal service change required by the shared lifecycle contract; do not add automatic retry.

### Task 3: Frontend rendering and persisted polling

**Files:**
- Modify: `web/static/app.js`
- Test: `tests/speaking-report-scoring-state.test.js`

- [ ] Extend static tests for `unscored`, `scoring`, `failed`, list/detail parity assumptions, and disabled regenerate markup while scoring.
- [ ] Run the Node test and `node --check` before implementation changes to establish RED where applicable.
- [ ] Update list/manager/detail rendering and use persisted `ai_task.id` polling after history loads; refresh detail/list from the backend on terminal state.
- [ ] Run the Node tests and syntax check.

### Task 4: Quality verification

**Files:**
- No new production files.

- [ ] Run targeted Django speaking tests, `manage.py check`, Node tests, `node --check`, and `git diff --check`.
- [ ] Review the final diff for accidental changes to unrelated dirty files and confirm no service/tunnel commands were run.
- [ ] Run Trellis quality check and record any spec update needed.
