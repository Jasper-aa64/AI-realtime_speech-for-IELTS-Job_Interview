#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== Experiment 5 open-source reuse and WASM validation =="
echo "Repository: ${ROOT_DIR}"
echo

echo "== libfvad vendor and license contract =="
test -f "${ROOT_DIR}/third_party/libfvad/LICENSE"
test -f "${ROOT_DIR}/third_party/libfvad/PATENTS"
test -f "${ROOT_DIR}/third_party/libfvad/AUTHORS"
test -f "${ROOT_DIR}/third_party/libfvad/include/fvad.h"
LIBFVAD_FILE_COUNT="$(find "${ROOT_DIR}/third_party/libfvad" -type f | wc -l | tr -d ' ')"
if [[ "${LIBFVAD_FILE_COUNT}" -lt 20 ]]; then
  echo "Expected vendored libfvad source files, found only ${LIBFVAD_FILE_COUNT}." >&2
  exit 1
fi
echo "libfvad vendor files present (${LIBFVAD_FILE_COUNT} files)."
echo

echo "== libfvad integration evidence =="
rg -n '#include "fvad.h"|fvad_new|fvad_set_sample_rate|fvad_set_mode|fvad_process' \
  "${ROOT_DIR}/src/ielts/audio_core.cpp" >/dev/null
rg -n 'third_party/libfvad/src/fvad\.c|fvad_vendor|target_link_libraries\(audio_core_test' \
  "${ROOT_DIR}/CMakeLists.txt" >/dev/null
rg -n 'third_party/libfvad/src/fvad\.c|emcc -c|em\+\+ -c|audio_core_wasm\.js' \
  "${ROOT_DIR}/scripts/build_audio_core_wasm.sh" >/dev/null
rg -n '_audio_core_is_speech_webrtc' \
  "${ROOT_DIR}/src/ielts/audio_core_wasm.cpp" \
  "${ROOT_DIR}/web/static/wasm/audio_core_demo.js" >/dev/null
echo "Native, CMake, WASM wrapper, and browser demo integration evidence passed."
echo

echo "== C++ native VAD tests =="
if [[ ! -f "${ROOT_DIR}/build/CMakeCache.txt" ]]; then
  cmake -S "${ROOT_DIR}" -B "${ROOT_DIR}/build"
fi
cmake --build "${ROOT_DIR}/build" --target audio_core_test
ctest --test-dir "${ROOT_DIR}/build" -R audio_core_test --output-on-failure
echo

echo "== WASM build =="
if ! command -v emcc >/dev/null 2>&1 && [[ -f "${HOME}/devtools/emsdk/emsdk_env.sh" ]]; then
  # shellcheck disable=SC1091
  EMSDK_QUIET=1 source "${HOME}/devtools/emsdk/emsdk_env.sh" >/dev/null
fi
"${ROOT_DIR}/scripts/build_audio_core_wasm.sh"
test -f "${ROOT_DIR}/web/static/wasm/audio_core_wasm.js"
test -f "${ROOT_DIR}/web/static/wasm/audio_core_wasm.wasm"
git -C "${ROOT_DIR}" check-ignore -v \
  web/static/wasm/audio_core_wasm.js \
  web/static/wasm/audio_core_wasm.wasm
echo

echo "== WASM demo JavaScript syntax =="
node --check "${ROOT_DIR}/web/static/wasm/audio_analyzer.js"
node --check "${ROOT_DIR}/web/static/wasm/audio_core_demo.js"
node --check "${ROOT_DIR}/web/static/wasm/audio_frame_processor.js"
node --check "${ROOT_DIR}/web/static/wasm/audio_worklet_demo.js"
echo

echo "== static serving MIME smoke =="
python3 - "${ROOT_DIR}" <<'PY'
import contextlib
import functools
import http.server
import pathlib
import time
import socketserver
import sys
import threading
import urllib.request

root = pathlib.Path(sys.argv[1])
wasm_dir = root / "web" / "static" / "wasm"
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(wasm_dir))

with contextlib.ExitStack() as stack:
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    stack.callback(server.server_close)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stack.callback(server.shutdown)
    port = server.server_address[1]
    time.sleep(0.1)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    response = opener.open(f"http://127.0.0.1:{port}/audio_core_wasm.wasm", timeout=5)
    content_type = response.headers.get("Content-Type", "")
    if "application/wasm" not in content_type:
        raise SystemExit(f"Expected application/wasm, got {content_type!r}")
    if len(response.read(64)) == 0:
        raise SystemExit("Generated wasm response was empty.")
print("WASM MIME smoke passed.")
PY
echo

echo "Experiment 5 open-source reuse and WASM validation passed."
