# Diagnose And Fix Examiner Audio Tearing

## Goal

Find and fix the recurring examiner TTS playback tearing/stutter regression in the speaking practice flow, especially the P1 fixed prompts.

## Problem Summary

The issue existed intermittently before, disappeared in a frozen/stable version, and resurfaced after recent large frontend/audio changes. A previous phase-guard experiment made the issue worse and has been reverted from the active playback path.

## Scope

- Compare stable/frozen behavior against current behavior.
- Preserve the core `<audio>` playback path unless evidence shows it is the root cause.
- Prefer low-risk isolation and diagnostics over speculative rewrites.
- Verify P1 first prompt and second prompt playback, because the second prompt historically exposes the regression most clearly.

## Acceptance Criteria

- No undefined playback-phase variables or half-applied diagnostic state remains in `web/static/app.js`.
- Examiner audio playback path runs without JS syntax/runtime errors.
- A clear diagnostic plan is available for reproducing the issue with `audio_debug=1`.
- Any functional fix must be minimal and reversible.

## Out of Scope

- Rewriting streaming follow-up.
- Reworking the whole practice state machine.
- Subagent usage.
