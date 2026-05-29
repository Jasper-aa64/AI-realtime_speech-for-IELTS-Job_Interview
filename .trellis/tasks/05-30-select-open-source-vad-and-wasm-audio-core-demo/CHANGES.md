# CHANGES

## Summary

Prepared the Experiment 5 foundation for open-source audio reuse and browser-side WASM without changing the production IELTS practice flow.

## Files Changed

- `.gitignore`
- `src/ielts/audio_core_wasm.cpp`
- `scripts/build_audio_core_wasm.sh`
- `web/static/wasm/audio_core_demo.html`
- `web/static/wasm/audio_core_demo.js`
- `软件构造/实验5_开源复用与WASM方案.md`
- `.trellis/tasks/05-30-select-open-source-vad-and-wasm-audio-core-demo/prd.md`

## Design Decision

Selected `libfvad` as the planned Experiment 5 open-source audio dependency because it is a standalone BSD-3-Clause C library based on WebRTC VAD. Actual vendoring/integration is intentionally left to the next task.

## WASM Scaffold

The repo now has an Emscripten build path:

```bash
scripts/build_audio_core_wasm.sh
```

This generates ignored artifacts:

- `web/static/wasm/audio_core_wasm.js`
- `web/static/wasm/audio_core_wasm.wasm`

The standalone demo page is:

```text
web/static/wasm/audio_core_demo.html
```

## Validation

Run:

```bash
bash -n scripts/build_audio_core_wasm.sh
c++ -std=c++17 -Iinclude -c src/ielts/audio_core_wasm.cpp -o /tmp/audio_core_wasm.o
cmake --build build --target audio_core_test
ctest --test-dir build -R audio_core_test --output-on-failure
node --check web/static/wasm/audio_core_demo.js
```

