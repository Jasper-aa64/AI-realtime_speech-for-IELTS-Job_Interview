# Overnight Headless Report

Date: 2026-05-30

Mode: no-key, no-human, self-verifying work only.

## Summary

The unattended queue was continued after Phase 2.3 had already been completed.
The remaining work focused on safe frontend modularization because those cuts do
not require ASR credentials, browser microphone validation, or product decisions.

Final validation:

- Django full test suite: `272/272` passed
- Django system check: passed
- Frontend syntax checks: passed for `app.js` and all newly extracted modules
- Remaining working tree state: `backend_django/db.sqlite3` only

## Completed Work

### A. Phase 2.3 realtime ASR logic layer

Status: completed before this continuation.

Commits:

- `bb4986c` - `feat: stream realtime ASR events over PCM websocket`
- `1ac7ebf` - `chore(task): archive 05-30-phase2-realtime-asr-logic-layer`
- `6f1f980` - `chore: record journal`

What is covered:

- `/ws/realtime/pcm/` accepts realtime PCM frames and ASR control events.
- PCM frames are queued into the realtime ASR provider logic.
- Fake websocket tests cover interim, final, done, and error event forwarding.
- Frontend `?realtime_pcm=1` can consume `asr_*` events and update live transcript state.

Blocked real-world validation:

- Real OpenSpeech/VolcEngine endpoint validation still requires user-provided
  ASR credentials and a real browser microphone run.

### B. app.js modularization

Status: advanced by four safe extraction knives.

Commits:

- `ad66a06` - `refactor: extract candidate profile module`
- `3e9ab13` - `refactor: extract corpus markdown editor module`
- `17b4bcd` - `refactor: extract realtime pcm uplink module`
- `7c6aceb` - `refactor: extract speaking audio preprocessor runtime`

Extracted modules:

- `web/static/candidate-profile.js`
- `web/static/corpus-markdown-editor.js`
- `web/static/realtime-pcm-uplink.js`
- `web/static/speaking-audio-preprocessor-runtime.js`

Line-count movement:

- `web/static/app.js`: `8352` lines after `candidate-profile` extraction -> `7892` lines now
- Net reduction during this continuation: `460` lines from `app.js`

Validation per knife:

- `node --check` for the touched frontend modules and `app.js`
- `python backend_django/manage.py check`
- `apps.common` Django tests for static route coverage
- `git diff --check`

Final validation:

- `node --check web/static/app.js`
- `node --check web/static/corpus-markdown-editor.js`
- `node --check web/static/realtime-pcm-uplink.js`
- `node --check web/static/speaking-audio-preprocessor-runtime.js`
- `node --check web/static/candidate-profile.js`
- `node --check web/static/examiner-audio-diagnostics.js`
- `python backend_django/manage.py check`
- `python backend_django/manage.py test`

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

### C. Continue `speaking/services.py` split

Deferred.

Reason: Phase 2 realtime validation is now the higher-value next integration
checkpoint, while `speaking/services.py` extraction should happen one knife at a
time after the ASR logic layer is accepted.

Current baseline:

- `backend_django/apps/speaking/services.py`: `4387` lines

### D. Add more tests

Deferred.

Reason: the current full Django suite is green at `272` tests. New tests should
be added with the next behavior-bearing knife rather than as speculative churn.

## Current Working Tree

At report time, the only remaining dirty file is:

- `backend_django/db.sqlite3`

`backend_django/db.sqlite3` remains local runtime state and was not included in
any refactor commit.

## Next Safe Step

1. If ASR credentials are ready, perform real OpenSpeech/VolcEngine validation
   for Phase 2.3.
2. If credentials are not ready, continue `app.js` modularization with another
   low-risk view/controller extraction.
3. Keep `speaking/services.py` extraction as a separate one-knife-at-a-time
   refactor after the realtime path is verified.
