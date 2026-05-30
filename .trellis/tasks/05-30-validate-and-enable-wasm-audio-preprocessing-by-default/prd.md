# Validate and enable WASM audio preprocessing by default

## Goal

Make C++/WASM audio preprocessing the default recording preprocessor only after proving it works in a real browser and fails safely. The product baseline must remain usable: if WASM cannot load, speaking recording must continue without silent breakage.

## What I Already Know

- `audio_core_wasm.js` and `audio_core_wasm.wasm` are generated and statically served.
- The WASM build script already separates C and C++ compilation and has passed existing validation.
- `scripts/run_software_construction_deliverables_validation.sh` already verifies the Experiment 3/4/5 audio core path.
- The decision is to test the real browser path first, then change the default from `off` to `wasm-audio-core` only if demo and recording-path checks pass.
- Django did not previously serve `/wasm/*`; enabling the feature requires a minimal static route for WASM artifacts.

## Requirements

1. Demo smoke: open `web/static/wasm/audio_core_demo.html` through an HTTP server and verify the demo assertions pass.
2. Recording smoke: open the Django speaking UI with `?wasm_audio=wasm-audio-core`, start a speaking recording flow, and verify the WASM analyzer initializes and does not break recording.
3. Runtime serving: Django must serve `/wasm/*.js`, `/wasm/*.wasm`, and the demo HTML with correct content types.
4. Fallback smoke: simulate/inspect the failure path enough to confirm failed WASM initialization falls back without throwing an uncaught error or blocking recording.
5. If the above pass, change the default audio preprocessor from `off` to `wasm-audio-core`.
6. Do not touch unrelated WIP files. Stage only this task's files.

## Out of Scope

- No backend realtime gateway work.
- No C++ protocol/realtime service integration.
- No UI redesign.
- No changes to unrelated business-line dirty files.
- No push.

## Acceptance Criteria

- [x] Browser demo page reports all expected checks as passed.
- [x] Speaking recording page loads with `wasm_audio=wasm-audio-core` and initializes the WASM analyzer.
- [x] Django serves `/wasm/*` assets with correct content types.
- [x] WASM load failure path falls back cleanly.
- [x] Default config changes to `wasm-audio-core` only after the browser checks pass.
- [x] Relevant JS syntax/unit validation passes.
- [x] Work is committed without unrelated dirty files.
