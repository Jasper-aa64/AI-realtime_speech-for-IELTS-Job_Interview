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
  "${ROOT_DIR}/third_party/libfvad/src/fvad.c" \
  "${ROOT_DIR}/third_party/libfvad/src/signal_processing/division_operations.c" \
  "${ROOT_DIR}/third_party/libfvad/src/signal_processing/energy.c" \
  "${ROOT_DIR}/third_party/libfvad/src/signal_processing/get_scaling_square.c" \
  "${ROOT_DIR}/third_party/libfvad/src/signal_processing/resample_48khz.c" \
  "${ROOT_DIR}/third_party/libfvad/src/signal_processing/resample_by_2_internal.c" \
  "${ROOT_DIR}/third_party/libfvad/src/signal_processing/resample_fractional.c" \
  "${ROOT_DIR}/third_party/libfvad/src/signal_processing/spl_inl.c" \
  "${ROOT_DIR}/third_party/libfvad/src/vad/vad_core.c" \
  "${ROOT_DIR}/third_party/libfvad/src/vad/vad_filterbank.c" \
  "${ROOT_DIR}/third_party/libfvad/src/vad/vad_gmm.c" \
  "${ROOT_DIR}/third_party/libfvad/src/vad/vad_sp.c" \
  -I"${ROOT_DIR}/include" \
  -I"${ROOT_DIR}/third_party/libfvad/include" \
  -I"${ROOT_DIR}/third_party/libfvad/src" \
  -std=c++17 \
  -O3 \
  -sMODULARIZE=1 \
  -sEXPORT_ES6=1 \
  -sENVIRONMENT=web \
  -sALLOW_MEMORY_GROWTH=1 \
  -sEXPORTED_FUNCTIONS='["_malloc","_free","_audio_core_normalized_rms","_audio_core_normalized_peak","_audio_core_is_speech","_audio_core_is_speech_webrtc","_audio_core_trim_silence","_audio_core_resample_linear"]' \
  -o "${OUT_JS}"

echo "Built ${OUT_JS}"
echo "Open web/static/wasm/audio_core_demo.html through the Django/static server or a local static server."
