# Select Open Source VAD And WASM Audio Core Demo

## Goal

Prepare the Experiment 5 foundation without changing the mature browser-first IELTS product flow:

1. Select the open-source audio library that will satisfy the coursework reuse requirement.
2. Add a minimal `audio_core` WebAssembly demo scaffold so the extracted C++ core can run in the browser once Emscripten is installed.

## Baseline Principle

The existing P1/P2/P3/Mock, writing, report, corpus, and Takeaway flows are the product baseline. This task must not wire WASM into those flows yet.

## Decision

Use `libfvad` as the planned open-source VAD integration target.

Reason:

- It is a standalone C library based on WebRTC VAD.
- It avoids pulling the full WebRTC native tree into this project.
- It has a small C API and BSD-3-Clause license, which is suitable for browser-side WASM reuse later.

Current task only records the selection and creates the WASM scaffold for the existing `audio_core`. Actual `libfvad` vendoring/integration is a separate follow-up task.

## Scope

- Add an Experiment 5 architecture/selection note under `软件构造/`.
- Add an Emscripten-compatible C ABI wrapper for `ielts::audio`.
- Add a build script for generating browser WASM artifacts.
- Add a standalone demo page and JS harness under `web/static/wasm/`.
- Ignore generated `.js`/`.wasm` artifacts.

## Out Of Scope

- No live P1/P2/P3 recording integration.
- No generated `.wasm` commit.
- No `libfvad` source vendoring yet.
- No Django API changes.
- No old `web/ielts_server.py` changes.
- No replacement of browser recording UX.

## Acceptance Criteria

- [ ] Document WebRTC VAD / `libfvad`, SpeexDSP, and libsamplerate trade-offs.
- [ ] Select one open-source library for Experiment 5 and explain why.
- [ ] Add `src/ielts/audio_core_wasm.cpp` with a small C ABI around the pure C++ functions.
- [ ] Add `scripts/build_audio_core_wasm.sh`.
- [ ] Add `web/static/wasm/audio_core_demo.html`.
- [ ] Add `web/static/wasm/audio_core_demo.js`.
- [ ] Generated `audio_core_wasm.js` and `audio_core_wasm.wasm` are ignored by git.
- [ ] If Emscripten is unavailable, the build script fails with an explicit install hint.
- [ ] Native C++ tests still pass.
- [ ] JS syntax check for the demo passes.

## Validation

Required locally:

```bash
bash -n scripts/build_audio_core_wasm.sh
c++ -std=c++17 -Iinclude -c src/ielts/audio_core_wasm.cpp -o /tmp/audio_core_wasm.o
cmake --build build --target audio_core_test
ctest --test-dir build -R audio_core_test --output-on-failure
node --check web/static/wasm/audio_core_demo.js
```

If Emscripten is installed:

```bash
scripts/build_audio_core_wasm.sh
```

Then open:

```text
web/static/wasm/audio_core_demo.html
```

