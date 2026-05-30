#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON:-${ROOT_DIR}/.venv-django/bin/python}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

echo "== Experiment 3 TDD validation =="
echo "Repository: ${ROOT_DIR}"
echo

echo "== C++ audio_core native tests =="
if [[ ! -f "${ROOT_DIR}/build/CMakeCache.txt" ]]; then
  cmake -S "${ROOT_DIR}" -B "${ROOT_DIR}/build"
fi
cmake --build "${ROOT_DIR}/build" --target audio_core_test
ctest --test-dir "${ROOT_DIR}/build" -R audio_core_test --output-on-failure
echo

echo "== WASM build and artifact contract =="
bash -n "${ROOT_DIR}/scripts/build_audio_core_wasm.sh"
"${ROOT_DIR}/scripts/build_audio_core_wasm.sh"
git -C "${ROOT_DIR}" check-ignore -v \
  web/static/wasm/audio_core_wasm.js \
  web/static/wasm/audio_core_wasm.wasm
echo

echo "== Frontend/WASM syntax and unit checks =="
node --check "${ROOT_DIR}/web/static/wasm/audio_analyzer.js"
node --check "${ROOT_DIR}/web/static/wasm/audio_core_demo.js"
node --check "${ROOT_DIR}/web/static/wasm/audio_frame_processor.js"
node --check "${ROOT_DIR}/web/static/wasm/audio_worklet_demo.js"
node --check "${ROOT_DIR}/web/static/wasm/speaking_audio_preprocessor.js"
node --check "${ROOT_DIR}/scripts/test_wasm_audio_preprocessor_metrics.mjs"
node --no-warnings "${ROOT_DIR}/scripts/test_wasm_audio_preprocessor_metrics.mjs"
echo

echo "== Django AI and speaking metrics regressions =="
"${PYTHON_BIN}" "${ROOT_DIR}/backend_django/manage.py" test \
  apps.ai \
  apps.speaking.tests.SpeakingRuntimeApiTests.test_turn_complete_persists_audio_preprocessing_metrics \
  -v 1
echo

echo "Experiment 3 TDD validation passed."
