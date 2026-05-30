# Software Construction Experiment 3 TDD Validation Layer

## Goal

Create a repeatable TDD validation layer for the current refactor line without changing product behavior. The task should make the already-built `audio_core`, WASM demo/preprocessor, and `apps.ai` provider-adapter refactor easy to verify from one documented command set for software construction experiment 3.

## What I Already Know

- The product baseline is mature and should not be redesigned in this task.
- C++ `audio_core` already has a native `audio_core_test` CTest target.
- `scripts/build_audio_core_wasm.sh` builds generated WASM artifacts and those artifacts are intentionally ignored by git.
- `web/static/wasm/speaking_audio_preprocessor.js` now summarizes per-turn preprocessing metrics.
- Django speaking has a regression test for server-side metrics sanitization/persistence.
- `backend_django/apps/ai/provider_adapters.py` has already been refactored to Strategy / Template Method / Adapter / ProviderChain and `apps.ai` tests pass.

## Requirements

- Add a lightweight unit test for the browser-side preprocessing summary function.
- Add a single validation script that runs the experiment 3 safety checks across C++, WASM, frontend syntax, JS summary behavior, and Django AI/speaking persistence.
- Keep the task as testing/verification only: no visible UI changes, no API contract changes, no database migration, no product flow changes.
- Do not commit generated `audio_core_wasm.js/.wasm`.
- Do not touch unrelated dirty files already in the worktree.

## Acceptance Criteria

- [x] A JS test verifies `summarizeSpeakingAudioPreprocessingMetrics()` clamps frame counts, computes ratios, rounds values, and omits raw samples.
- [x] A shell validation script runs native `audio_core_test`, the WASM build, syntax checks, the JS metrics test, Django `apps.ai`, and the speaking metrics persistence regression.
- [x] The validation script fails fast on any failed command.
- [x] Generated WASM artifacts remain ignored by git.
- [x] Existing product code behavior is unchanged.

## Definition of Done

- [x] `bash -n scripts/run_experiment3_tdd_validation.sh`
- [x] `node --check scripts/test_wasm_audio_preprocessor_metrics.mjs`
- [x] `scripts/run_experiment3_tdd_validation.sh`
- [x] `git status` shows only scoped task files staged/committed, with unrelated dirty files preserved.

## Out of Scope

- Reworking speaking runtime UX.
- Adding a real-time gateway.
- Changing `apps.ai` provider routing behavior.
- Changing writing/speaking scoring prompts.
- Changing committed sample database contents.

## Technical Notes

- Relevant specs:
  - `.trellis/spec/backend/index.md`
  - `.trellis/spec/backend/quality-guidelines.md`
  - `.trellis/spec/frontend/wasm-audio-guidelines.md`
- The validation script should be usable by the software construction report as experiment 3 evidence.
