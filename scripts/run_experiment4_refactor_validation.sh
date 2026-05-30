#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== Experiment 4 refactor validation =="
echo "Repository: ${ROOT_DIR}"
echo

echo "== audio_core purity boundary =="
FORBIDDEN_INCLUDE_PATTERN='#include <(Q[A-Za-z0-9_/.-]*|Qt[A-Za-z0-9_/.-]*|portaudio|pa_[A-Za-z0-9_/.-]*|curl|asio|boost/asio|websocketpp|Python\.h|django)'
if rg -n "${FORBIDDEN_INCLUDE_PATTERN}" \
  "${ROOT_DIR}/include/ielts/audio_core.h" \
  "${ROOT_DIR}/src/ielts/audio_core.cpp"; then
  echo "audio_core must stay free of UI, device, network, Python, and Django dependencies." >&2
  exit 1
fi
echo "audio_core dependency boundary passed."
echo

echo "== audio_core API evidence =="
rg -n "NormalizedRms|NormalizedPeak|AnalyzeFrame|AnalyzeFrameWithVad|TrimSilence|ResampleLinear" \
  "${ROOT_DIR}/include/ielts/audio_core.h" \
  "${ROOT_DIR}/src/ielts/audio_core.cpp" >/dev/null
echo "audio_core extracted API is present."
echo

if ! command -v emcc >/dev/null 2>&1 && [[ -f "${HOME}/devtools/emsdk/emsdk_env.sh" ]]; then
  # shellcheck disable=SC1091
  source "${HOME}/devtools/emsdk/emsdk_env.sh" >/dev/null
fi

echo "== reuse Experiment 3 TDD validation =="
"${ROOT_DIR}/scripts/run_experiment3_tdd_validation.sh"
echo

echo "== generated WASM artifact contract =="
git -C "${ROOT_DIR}" check-ignore -v \
  web/static/wasm/audio_core_wasm.js \
  web/static/wasm/audio_core_wasm.wasm
echo

echo "Experiment 4 refactor validation passed."
