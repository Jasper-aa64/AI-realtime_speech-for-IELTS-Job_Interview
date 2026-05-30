# WASM Audio Guidelines

> Contracts for the standalone C++ `audio_core` WebAssembly demos and future
> browser-side audio preprocessing work.

## Scenario: Standalone AudioWorklet to WASM Analyzer Demo

### 1. Scope / Trigger

- Trigger: Browser-side microphone frames are routed through a selectable
  analyzer abstraction so the same AudioWorklet frame stream can use either a
  JavaScript fallback analyzer or generated C++ `audio_core` WebAssembly.
- Scope: Standalone files under `web/static/wasm/` only.
- Out of scope: Production P1/P2/P3 recording flows in `web/static/app.js`.
  Product integration must be a separate feature-flagged task.

### 2. Signatures

- Build command:
  ```bash
  scripts/build_audio_core_wasm.sh
  ```
- Generated artifacts, intentionally ignored by git:
  ```text
  web/static/wasm/audio_core_wasm.js
  web/static/wasm/audio_core_wasm.wasm
  ```
- Standalone smoke pages:
  ```text
  web/static/wasm/audio_core_demo.html
  web/static/wasm/audio_worklet_demo.html
  ```
- Analyzer factory:
  ```js
  await createAnalyzer("mock-rms", { threshold: 0.02 });
  await createAnalyzer("wasm-audio-core", { threshold: 0.02 });
  ```

### 3. Contracts

- `audio_frame_processor.js` runs inside `AudioWorkletGlobalScope` and should
  only capture/report frames. It must not import the generated Emscripten module.
- `audio_analyzer.js` runs on the main thread and owns analyzer selection:
  `Mock RMS` for deterministic fallback and `WASM audio_core` for generated
  C++ WASM.
- `WASM audio_core` requires `audio_core_wasm.js/.wasm` to exist. If loading
  fails, the UI may fall back to `Mock RMS` and must report the failure clearly.
- Emscripten builds must export:
  - `_malloc`
  - `_free`
  - audio wrapper functions such as `_audio_core_is_speech`
  - runtime `HEAP16`, because the browser demo writes `Int16Array` samples into
    WASM memory.
- C++ exception catching must be enabled for this wrapper so invalid frame
  errors return wrapper error codes instead of aborting the browser module.

### 4. Validation & Error Matrix

- `emcc` / `em++` missing -> build script exits `78` with install/activate
  instructions.
- Generated WASM missing -> `WASM audio_core` analyzer load fails and the demo
  reports fallback/error state.
- `.wasm` served with the wrong MIME type -> browser smoke is invalid; serve
  through a static server that returns `application/wasm`.
- Invalid WebRTC VAD frame length -> wrapper returns an error code such as `-1`;
  the browser must not abort.

### 5. Good/Base/Bad Cases

- Good: `audio_worklet_demo.html` can switch to `WASM audio_core`, receive
  microphone frames, and show `WASM audio_core analyzer is ready.`
- Base: Generated artifacts are absent; `Mock RMS` still works and the page is
  usable as a frame-stream demo.
- Bad: Production P1/P2/P3 flows silently depend on generated WASM artifacts or
  break when Emscripten artifacts are missing.

### 6. Tests Required

- Build generated artifacts:
  ```bash
  scripts/build_audio_core_wasm.sh
  ```
- Syntax-check standalone demo modules:
  ```bash
  node --check web/static/wasm/audio_analyzer.js
  node --check web/static/wasm/audio_core_demo.js
  node --check web/static/wasm/audio_frame_processor.js
  node --check web/static/wasm/audio_worklet_demo.js
  ```
- Keep native C++ tests green:
  ```bash
  cmake --build build --target audio_core_test
  ctest --test-dir build -R audio_core_test --output-on-failure
  ```
- Confirm generated artifacts are ignored:
  ```bash
  git check-ignore -v web/static/wasm/audio_core_wasm.js web/static/wasm/audio_core_wasm.wasm
  ```
- Browser smoke:
  - `audio_core_demo.html` reports `WASM smoke test passed.`
  - `audio_worklet_demo.html` can select `WASM audio_core`.

### 7. Wrong vs Correct

#### Wrong

```js
// Worklet scope: avoid loading generated Emscripten modules here.
import("./audio_core_wasm.js");
```

#### Correct

```js
// Worklet scope captures frames only.
this.port.postMessage({ type: "audio-frame", samples: frame }, [frame.buffer]);

// Main thread owns analyzer selection and WASM loading.
const analyzer = await createAnalyzer("wasm-audio-core", { threshold: 0.02 });
const result = analyzer.analyze(frame);
```

