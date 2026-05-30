# CHANGES

## Summary

Added an experiment 3 TDD validation layer that can verify the current C++ audio core, WASM browser preprocessing boundary, Django AI provider refactor, and speaking metrics persistence without changing product behavior.

## Files Changed

- `scripts/test_wasm_audio_preprocessor_metrics.mjs`
- `scripts/run_experiment3_tdd_validation.sh`
- `.trellis/tasks/05-30-software-construction-experiment3-tdd-validation-layer/prd.md`
- `.trellis/tasks/05-30-software-construction-experiment3-tdd-validation-layer/implement.jsonl`
- `.trellis/tasks/05-30-software-construction-experiment3-tdd-validation-layer/check.jsonl`

## Validation Coverage

- Native C++ `audio_core_test` build and CTest execution.
- Emscripten WASM build via `scripts/build_audio_core_wasm.sh`.
- Generated WASM artifact ignore contract.
- WASM demo JavaScript syntax checks.
- Browser-side `summarizeSpeakingAudioPreprocessingMetrics()` unit behavior.
- Django `apps.ai` regression suite.
- Django speaking metrics persistence regression.

## Behavior Notes

- No product UI, API, prompt, scoring, billing, or database schema behavior was changed.
- Generated `audio_core_wasm.js/.wasm` artifacts remain ignored by git.
- The validation script uses `set -euo pipefail` and fails fast.

## Validation

```text
bash -n scripts/run_experiment3_tdd_validation.sh
node --check scripts/test_wasm_audio_preprocessor_metrics.mjs
scripts/run_experiment3_tdd_validation.sh

Experiment 3 TDD validation passed.
```
