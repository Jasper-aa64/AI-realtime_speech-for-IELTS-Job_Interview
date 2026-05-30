# Project Refactor With Software Construction Assignments

## Goal

Plan a refactor path for the IELTS Studio project while using the same work as evidence for Software Construction experiments 2-5. The plan should let product-quality engineering work and coursework deliverables reinforce each other instead of becoming two disconnected efforts.

## What I Already Know

* The current product is primarily a Django backend plus `web/static` single-page frontend.
* `web/ielts_server.py` is deprecated and should be used as reference only, not as the main runtime.
* Main frontend files are `web/static/index.html`, `web/static/app.js`, and `web/static/styles.css`.
* Main backend package is `backend_django/`, split into `accounts`, `speaking`, `writing`, `ai`, and `billing`.
* Current sensitive engineering areas:
  * Speaking AI follow-up and report generation must use real Codex CLI where possible, with honest fallback metadata.
  * Writing scoring should use the Django durable AI task worker.
  * Writing Task 1 image prompt UX and loading performance are active concerns.
  * Writing reports should match the speaking report structure.
* The existing Software Construction files are under `软件构造/`:
  * `软件构造_实验1_报告.docx`
  * `软件构造-实验2.pptx`
  * `软件构造-实验3.pptx`
  * `软件构造-实验4.pptx`
  * `软件构造-实验5.pptx`

## Coursework Requirements Extracted

### Experiment 2

Use design patterns / object-oriented class design to implement the business system from Experiment 1.

Scoring focus:
* Detailed explanation of the implementation process.
* Demonstration of implementation effect.

### Experiment 3

Use test-driven development based on the Experiment 2 system.

Scoring focus:
* Designed test cases.
* Automated test scripts.
* Defects exposed by tests and how they were fixed.

### Experiment 4

Refactor software code with implementation or design defects.

Scoring focus:
* Detailed explanation of code/design defects.
* Detailed explanation of refactoring changes.
* Before/after comparison.

### Experiment 5

Reuse open-source software resources and integrate them into the current system.

Scoring focus:
* Explain what open-source module was downloaded and provide its URL.
* Explain the module's function and implementation logic.
* Explain how it was integrated into the current system.
* Compare system functionality before and after integration.

## Important Discovery

The current Experiment 1 report describes a different business scenario:

* "MCP 多 Agent 智能代码生成与训练数据合成系统"
* C++ MCP Server
* Python LangGraph multi-agent system
* trajectory collection / quality analysis / SFT-DPO export
* future GUI management console and database

This does not directly match the current IELTS Studio product. Before implementation/report writing, we need choose a narrative strategy:

1. Continue Experiment 1's MCP multi-agent story and implement coursework around a smaller MCP/agent module.
2. Rewrite/reframe Experiment 1 so IELTS Studio becomes the business scenario.
3. Bridge them by treating IELTS Studio's AI worker / prompt assistant / report generation as the "multi-agent training/coaching system" implementation.

## Proposed Refactor-To-Coursework Mapping

### Experiment 2: OO / Pattern-Based Design

Candidate implementation themes:
* Extract AI provider strategy objects from ad-hoc Codex calls.
* Extract speaking report generation services into composable builders.
* Extract writing prompt search / image prompt loading as reusable services.
* Introduce clear domain boundaries:
  * `SpeakingAttemptService`
  * `SpeakingScoringService`
  * `WritingScoringService`
  * `PromptBankService`
  * `ProviderAdapter`

Patterns likely useful for report:
* Strategy: provider adapters for Codex / fallback / future OpenAI direct API.
* Template Method or Pipeline: scoring/report generation steps.
* Repository-like service boundary: prompt banks and reports.
* Observer/Worker pattern: AI task queue and completion notification.

### Experiment 3: TDD

Use existing Django tests and add focused tests around the refactored areas:
* AI provider success/failure behavior.
* Speaking follow-up generated vs fallback metadata.
* Writing score task success/failure without fake reports.
* Task 1 prompt image loading metadata/API payload.
* Report clone/revision behavior.

Deliverable evidence:
* Test case table.
* Automated test scripts: Django test commands + JS syntax check.
* Defects found and fixed, especially fake fallback / blocking Codex / image loading performance.

### Experiment 4: Refactoring Bad Smells

Strong candidates:
* Large `web/static/app.js` doing too many responsibilities.
* Large `backend_django/apps/speaking/services.py` mixing attempt lifecycle, Codex calls, scoring, report building, TTS, corpus, and training.
* Deprecated `web/ielts_server.py` still containing old logic and confusing ownership.
* Duplicated prompt/report formatting logic between speaking and writing.
* Synchronous blocking Codex calls on user-facing flows.

Refactor deliverables:
* Before/after dependency graph.
* Extracted service/classes/functions.
* Measurable improvements: fewer synchronous calls, clearer fallback metadata, smaller functions, tests.

### Experiment 5: Open-Source Reuse

Candidate integrations:
* Pot-App Caiyun translation plugin reference for Language Takeaway translation behavior.
* Browser native lazy loading / priority hints are standards, but not a downloaded software module.
* Vditor markdown editor already appears in the project for corpus editing; it is an open-source reusable component and may fit Experiment 5 well.
* Potential image optimization tooling such as `cwebp` can be used, but CLI tooling alone may be weaker than a library/component integration.

Best candidate for Experiment 5:
* Vditor markdown editor or translation plugin integration, because it has visible before/after UI functionality.

## C++ Placement Under Real Deployment Constraints

The project currently has old C++/Qt code under `src/` and `include/`, but the web product runtime is Django + browser SPA. If the goal is a deployable web product, C++ cannot be treated as if it will automatically run everywhere:

* Local development is macOS arm64, with paths such as `vcpkg_installed/arm64-osx`.
* A real server is likely Linux x86_64, so C++ binaries must be rebuilt or packaged per target platform.
* `codex exec` is a local developer CLI dependency and is not a reliable production server dependency; production AI should eventually move behind HTTP provider adapters.

Candidate C++ roles:

1. **Server-side C++ sidecar**
   * Django invokes a compiled C++ binary/service for CPU-heavy audio work such as decode, VAD, resampling, or feature extraction.
   * Good for demonstrating systems/IPC/server performance.
   * Deployment cost: Docker/Linux build toolchain, binary packaging, process supervision.

2. **Browser-side C++ to WebAssembly**
   * Compile selected audio logic to WASM and run it in the browser before upload.
   * Best fit for web deployment: lower server load and stronger portfolio story.
   * Porting cost: browser audio APIs replace desktop audio assumptions such as PortAudio/Qt.

3. **Keep C++ as a separate portfolio project**
   * Web product stays Python/Django; C++/Qt is documented as the earlier native prototype.
   * Lowest product risk, but weaker integration story for coursework/refactor.

Current planning preference:
* If C++ must be part of the deployed web story, prefer a narrow WASM proof-of-concept for audio preprocessing rather than a broad server sidecar.
* If the coursework deadline is tight, use the Django AI/provider/report refactor as the main coursework object and keep C++ as historical context.

Clarification on browser audio APIs:
* Browsers already provide basic audio capabilities such as microphone capture, playback, recording containers, and Web Audio processing.
* Browsers do not provide a portable, product-controlled IELTS-specific VAD / segmentation / deterministic resampling pipeline out of the box.
* For the current product, plain browser APIs may be enough for recording and upload. C++ to WASM only becomes valuable if we need deterministic audio preprocessing, want to reuse existing C++ algorithms, or want a stronger portfolio/coursework story.

Performance/refactor ranking for C++ reuse:
* **Highest value**: isolate a small audio preprocessing core and compile it to WASM for browser-side VAD / silence trimming / normalization / deterministic resampling. This has a credible performance and deployment story.
* **Medium value**: package the same audio preprocessing core as a server-side CLI/sidecar for Linux deployments. Easier to benchmark server-side, but adds deployment complexity.
* **Low value**: reuse C++ for question-bank search, report rendering, or scoring orchestration. Current bottlenecks there are API payload size, browser rendering, database queries, and model latency, not CPU-bound C++ work.
* **Not suitable**: replacing AI generation/report reasoning with C++; the bottleneck is external model latency and prompt/output design.

Non-C++ optimization opportunities:
* Convert large Writing Task 1 images to optimized WebP/AVIF plus thumbnails; use full-size images only after selection.
* Reduce initial SPA fan-out: do not load every report, corpus, takeaway, writing prompt, and history payload on first page load.
* Split large frontend logic by route or feature so first paint does not parse the whole product.
* Add compact list/detail APIs where reports or corpus entries currently return heavy payloads.
* Move Codex/model calls fully behind durable async tasks and UI notifications; never block interactive save/start flows.
* Cache stable assets and prompt metadata, but keep user data fresh.
* Add database indexes/pagination for report lists, corpus entries, and takeaway lists once data grows.

## Realtime Speaking Direction

The strongest C++ reuse story is not "find a small place for C++"; it is to make the web product grow toward the original C++ realtime speaking vision:

```text
Browser microphone
  -> audio preprocessing core (C++ compiled to WASM, later)
  -> browser WebSocket audio stream
  -> C++ realtime speech gateway on Linux
  -> upstream streaming ASR
  -> Django stores transcript / drives UI / scores reports
```

Target architecture:

1. **C++ audio core**
   * Pure, IO-free audio preprocessing functions.
   * Testable locally with deterministic sample fixtures.
   * Can later compile to WASM for browser-side VAD / trimming / resampling.

2. **C++ realtime gateway**
   * Long-running Linux service.
   * Reuses/refactors `realtime_client.cpp` and `protocol.cpp`.
   * Bridges browser/Django session flow to the upstream streaming ASR service.

3. **Django orchestration**
   * Owns attempts, turns, reports, user state, billing, and fallback.
   * Keeps the existing batch upload/score flow as a demo-safe fallback.

Decision:
* Use **Scheme A** as the long-term target: a C++ realtime bridge service is allowed because the deployment target is a Linux server that can run long-lived native services.
* Start with `audio_core` extraction first. It is the lowest-risk foundation for both WASM and server gateway work.
* Keep the coursework deliverable order readable as Experiment 2 -> 3 -> 4 -> 5, but implementation may lightly overlap: Experiment 2 defines interfaces/patterns while Experiment 4's audio-core extraction supplies the concrete C++ refactor evidence.
* Keep the existing browser/Django batch flow as the product baseline. Realtime and WASM should enter as optional acceleration/fallback-aware layers, not as a forced rewrite.

Risk note:
* Emscripten alone may not satisfy Experiment 5's "reuse open-source software resource" requirement if the teacher expects an actual library/component. A safer Experiment 5 story should pair C++->WASM with a concrete open-source dependency such as WebRTC VAD, SpeexDSP, libsamplerate, or Vditor/translation integration depending on final scope.

## Requirements (Evolving)

* Keep production refactor aligned with the Django-first architecture.
* Do not implement new features in deprecated `web/ielts_server.py`.
* Preserve product behavior while refactoring.
* Treat the existing browser-first product flow as the primary product design. C++ realtime/WASM work must be incremental refactor/performance enhancement, not a replacement of the current UX or feature model.
* Do not redesign mature existing features just to showcase C++; preserve current P1/P2/P3/Mock, writing, reports, corpus, and Takeaway flows unless a change is explicitly approved.
* Produce coursework evidence as a byproduct of real changes:
  * screenshots,
  * before/after code,
  * test outputs,
  * diagrams,
  * defect lists,
  * open-source integration notes.

## Acceptance Criteria (Evolving)

* [ ] A single coursework narrative is chosen and documented.
* [ ] Experiment 2 implementation maps to real project refactor commits.
* [ ] Experiment 3 tests cover the refactored behavior and expose at least one real defect/fix.
* [ ] Experiment 4 identifies concrete code smells and shows before/after refactor.
* [ ] Experiment 5 integrates or documents a real open-source reusable module with before/after comparison.
* [ ] Work avoids committing local `backend_django/db.sqlite3`.

## Open Questions

* Should the coursework narrative continue the existing Experiment 1 MCP multi-agent system, or should we pivot/rewrite the narrative around IELTS Studio?
* Should C++ be integrated into the deployable web product, or kept as a separate native/portfolio artifact?

## Technical Notes

* Parsed `软件构造-实验2.pptx` through `软件构造-实验5.pptx` by extracting slide XML text.
* Parsed the beginning of `软件构造_实验1_报告.docx` with `python-docx`.
* Current working tree was already dirty before this planning task; avoid broad commits until the current implementation state is reconciled.
