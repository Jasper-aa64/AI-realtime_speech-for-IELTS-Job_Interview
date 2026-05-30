#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/web/static/wasm"
OUT_JS="${OUT_DIR}/audio_core_wasm.js"
BUILD_DIR="${ROOT_DIR}/build/audio_core_wasm"

if ! command -v emcc >/dev/null 2>&1 || ! command -v em++ >/dev/null 2>&1; then
  for env_file in \
    "${EMSDK_ENV:-}" \
    "${EMSDK:+${EMSDK}/emsdk_env.sh}" \
    "${ROOT_DIR}/emsdk/emsdk_env.sh" \
    "${HOME}/devtools/emsdk/emsdk_env.sh" \
    "${HOME}/emsdk/emsdk_env.sh"; do
    if [[ -n "${env_file}" && -f "${env_file}" ]]; then
      # shellcheck disable=SC1090
      EMSDK_QUIET=1 source "${env_file}" >/dev/null
      break
    fi
  done
fi

if ! command -v emcc >/dev/null 2>&1 || ! command -v em++ >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Emscripten compiler not found: emcc/em++

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

mkdir -p "${OUT_DIR}" "${BUILD_DIR}"

INCLUDES=(
  -I"${ROOT_DIR}/include"
  -I"${ROOT_DIR}/third_party/libfvad/include"
  -I"${ROOT_DIR}/third_party/libfvad/src"
)

C_SOURCES=(
  "${ROOT_DIR}/third_party/libfvad/src/fvad.c"
  "${ROOT_DIR}/third_party/libfvad/src/signal_processing/division_operations.c"
  "${ROOT_DIR}/third_party/libfvad/src/signal_processing/energy.c"
  "${ROOT_DIR}/third_party/libfvad/src/signal_processing/get_scaling_square.c"
  "${ROOT_DIR}/third_party/libfvad/src/signal_processing/resample_48khz.c"
  "${ROOT_DIR}/third_party/libfvad/src/signal_processing/resample_by_2_internal.c"
  "${ROOT_DIR}/third_party/libfvad/src/signal_processing/resample_fractional.c"
  "${ROOT_DIR}/third_party/libfvad/src/signal_processing/spl_inl.c"
  "${ROOT_DIR}/third_party/libfvad/src/vad/vad_core.c"
  "${ROOT_DIR}/third_party/libfvad/src/vad/vad_filterbank.c"
  "${ROOT_DIR}/third_party/libfvad/src/vad/vad_gmm.c"
  "${ROOT_DIR}/third_party/libfvad/src/vad/vad_sp.c"
)

CXX_SOURCES=(
  "${ROOT_DIR}/src/ielts/audio_core.cpp"
  "${ROOT_DIR}/src/ielts/audio_core_wasm.cpp"
)

OBJECTS=()

object_path() {
  local source_file="$1"
  local relative="${source_file#"${ROOT_DIR}/"}"
  printf '%s/%s.o' "${BUILD_DIR}" "${relative//\//_}"
}

for source_file in "${C_SOURCES[@]}"; do
  object_file="$(object_path "${source_file}")"
  emcc -c "${source_file}" "${INCLUDES[@]}" -O3 -o "${object_file}"
  OBJECTS+=("${object_file}")
done

for source_file in "${CXX_SOURCES[@]}"; do
  object_file="$(object_path "${source_file}")"
  em++ -c "${source_file}" "${INCLUDES[@]}" -std=c++17 -fexceptions -O3 -o "${object_file}"
  OBJECTS+=("${object_file}")
done

em++ \
  "${OBJECTS[@]}" \
  -fexceptions \
  -sMODULARIZE=1 \
  -sEXPORT_ES6=1 \
  -sENVIRONMENT=web \
  -sALLOW_MEMORY_GROWTH=1 \
  -sNO_DISABLE_EXCEPTION_CATCHING=1 \
  -sEXPORTED_FUNCTIONS='["_malloc","_free","_audio_core_normalized_rms","_audio_core_normalized_peak","_audio_core_is_speech","_audio_core_is_speech_webrtc","_audio_core_trim_silence","_audio_core_resample_linear"]' \
  -sEXPORTED_RUNTIME_METHODS='["HEAP16"]' \
  -o "${OUT_JS}"

echo "Built ${OUT_JS}"
echo "Open web/static/wasm/audio_core_demo.html through the Django/static server or a local static server."
