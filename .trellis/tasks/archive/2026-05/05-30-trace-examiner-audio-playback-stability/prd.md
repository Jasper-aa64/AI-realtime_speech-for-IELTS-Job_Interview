# Trace Examiner Audio Playback Stability

## Goal

Diagnose and fix the remaining examiner-audio playback stutter, especially the second fixed prompt (`Do you work or do you study?`) after the first prompt plays normally.

## Problem

A previous fix kept the preload cache warm, but local playback still has a stable mid-audio pause/stutter. The likely causes are not yet proven:

- cached `Audio` object is not ready enough when playback begins;
- the active playback uses a preloading `Audio` element whose buffering can still stall;
- concurrent TTS refresh/polling or stop/reset events interrupt the same URL;
- WASM/audio worklet initialization competes for main-thread/audio resources;
- browser media events (`waiting`, `stalled`, `suspend`, `emptied`) are not visible, so fixes are guesswork.

## Scope

- Add lightweight client-side examiner audio telemetry for preload/playback lifecycle.
- Make telemetry accessible from the console for local diagnosis.
- Prefer robust playback behavior over guessing from cache state.
- Preserve server TTS and existing practice flow.

## Acceptance Criteria

- [x] Console-accessible diagnostics show recent examiner audio events, including URL, turn id, phase, readyState, networkState, currentTime, duration, and timestamps.
- [x] Events include preload lifecycle (`loadstart`, `loadeddata`, `canplay`, `canplaythrough`, `waiting`, `stalled`, `suspend`, `error`) and playback lifecycle (`play`, `playing`, `waiting`, `stalled`, `ended`, `error`).
- [x] Starting playback does not reuse an actively buffering preload object in a way that hides failures; playback should use the visible/active `#examinerAudio` element while preloads only warm cache.
- [x] Fixed examiner audio cache remains warm across phase transitions.
- [x] WASM/audio preprocessor still starts only during recording and does not initialize during examiner playback.
- [x] Verification passes: `node --check web/static/app.js`, `manage.py check`, and `git diff --check`.

## Out of Scope

- Replacing VolcEngine TTS.
- Changing prompt text or speaking flow.
- Rewriting the recording pipeline.
