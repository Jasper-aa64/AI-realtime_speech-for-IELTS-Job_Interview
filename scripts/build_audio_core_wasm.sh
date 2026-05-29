#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/web/static/wasm"
OUT_JS="${OUT_DIR}/audio_core_wasm.js"

if ! command -v emcc >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Emscripten compiler not found: emcc

Install and activate Emscripten before building this demo:
  git clone https://github.com/emscripten-core/emsdk.git
  cd emsdk
  ./emsdk install latest
  ./emsdk activate latest
  source ./emsdk_env.sh

Then rerun:
  scripts/build_audio_core_wasm.sh
EOF
  exit 78
fi

mkdir -p "${OUT_DIR}"

emcc \
  "${ROOT_DIR}/src/ielts/audio_core.cpp" \
  "${ROOT_DIR}/src/ielts/audio_core_wasm.cpp" \
  -I"${ROOT_DIR}/include" \
  -std=c++17 \
  -O3 \
  -sMODULARIZE=1 \
  -sEXPORT_ES6=1 \
  -sENVIRONMENT=web \
  -sALLOW_MEMORY_GROWTH=1 \
  -sEXPORTED_FUNCTIONS='["_malloc","_free","_audio_core_normalized_rms","_audio_core_normalized_peak","_audio_core_is_speech","_audio_core_trim_silence","_audio_core_resample_linear"]' \
  -o "${OUT_JS}"

echo "Built ${OUT_JS}"
echo "Open web/static/wasm/audio_core_demo.html through the Django/static server or a local static server."

