# Overnight Headless Report

Date: 2026-05-30

Mode: no-key, no-human, self-verifying work only.

## Summary

The safe headless queue was evaluated against the current working tree.

- Completed: Phase 2.3 realtime ASR logic layer is already committed and archived.
- Blocked: real OpenSpeech/VolcEngine endpoint validation still requires user-provided ASR credentials and a real microphone run.
- Deferred: further `app.js` and `speaking/services.py` cuts are not safe to continue headlessly from the current dirty tree because both areas already contain unrelated WIP.

No production behavior was changed by this report.

## Completed Work

### A. Phase 2.3 realtime ASR logic layer

Status: completed before this report.

Commits:

- `bb4986c` - `feat: stream realtime ASR events over PCM websocket`
- `1ac7ebf` - `chore(task): archive 05-30-phase2-realtime-asr-logic-layer`
- `6f1f980` - `chore: record journal`

What is covered:

- `/ws/realtime/pcm/` accepts `start_asr` and `stop_asr` control messages.
- PCM frames are queued into the realtime ASR provider logic.
- Fake websocket tests cover interim, final, done, and error event forwarding.
- Frontend `?realtime_pcm=1` can consume `asr_*` events and update live transcript state.

Validation recorded at completion:

- `apps.speaking.test_asgi_channels`: 4/4 passed
- `apps.speaking.test_realtime_asr`: 4/4 passed
- `node --check web/static/app.js`: passed
- `python manage.py check`: passed
- Full Django suite: 272 tests passed
- `git diff --check`: passed

## Blocked / Human-Gated Items

### Real realtime ASR endpoint validation

Blocked on user-provided ASR environment configuration and a real browser microphone run.

Required facts:

- OpenSpeech/VolcEngine websocket URL
- App ID / access key / authentication headers
- Confirmed streaming interim/final event shape

Expected manual validation:

- Start a P1/P3 practice with `?realtime_pcm=1`.
- Speak one sentence.
- Confirm transcript appears while speaking or immediately after short pauses.
- Confirm fallback to the existing batch flow if ASR setup is missing or fails.

## Deferred Headless Work

### B. Continue `app.js` modularization

Deferred for this unattended pass.

Reason: `web/static/app.js` and `web/static/index.html` are already dirty with existing WIP. Continuing module extraction without a clean boundary risks mixing unrelated work into a refactor commit.

Current baseline:

- `web/static/app.js`: 8368 lines

### C. Continue `speaking/services.py` split

Deferred for this unattended pass.

Reason: multiple speaking service files are already dirty, including `services.py`, `tts_services.py`, `views.py`, `tests.py`, and `corpus_services.py`. Continuing service extraction headlessly risks mixing behavior changes, tests, and refactor movement.

Current baseline:

- `backend_django/apps/speaking/services.py`: 4387 lines
- `backend_django/apps/writing/services.py`: 605 lines

### D. Add more tests

Deferred.

Reason: the current dirty tree already contains speaking test changes. More tests should be added after those changes are classified and either committed or separated.

## Current Dirty Working Tree

At report time, the remaining dirty files were:

- `backend_django/apps/speaking/corpus_services.py`
- `backend_django/apps/speaking/services.py`
- `backend_django/apps/speaking/tests.py`
- `backend_django/apps/speaking/tts_services.py`
- `backend_django/apps/speaking/views.py`
- `backend_django/db.sqlite3`
- `docs/SPEC-streaming-examiner-followup-phase2.md`
- `web/static/app.js`
- `web/static/index.html`
- `docs/SPEC-overnight-headless.md` (to be committed with this report)

`backend_django/db.sqlite3` remains local state and must not be included in refactor commits.

## Next Safe Step

1. Commit this report and the overnight headless plan as documentation only.
2. Classify the existing dirty speaking and frontend files into their owning work streams.
3. After the tree is clean or isolated, resume either:
   - real ASR endpoint validation, if credentials are ready; or
   - one clean `app.js` extraction knife; or
   - one clean `speaking/services.py` extraction knife.
