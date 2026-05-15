# IELTS Speaking Simulator Web UI

## Goal

Build a dedicated Web UI for the IELTS Speaking Simulator so users can open a link, practice Part 1, Part 2, Part 3 individually, or run a full P1+P2+P3 mock exam from one polished browser experience. The product direction is link-first distribution: it should be easy to place on a blog, share with learners, and demo without asking users to build or install a desktop app.

## What I Already Know

* The CLI IELTS simulator is functionally running end to end.
* Verified locally on 2026-05-08:
  * `IELTSSpeakingSimulator` builds.
  * Existing `CppInterviewSystemQt` builds.
  * `IELTSSpeakingSimulator --help` exits successfully.
  * `ctest --test-dir build-ui-verify --output-on-failure` passes `6/6`.
* The current Qt UI exists only for the original C++ interview product:
  * Entry: `src/main_qt.cpp`
  * UI files: `include/ui/mainwindow.h`, `src/ui/mainwindow.cpp`, `src/ui/config_dialog.cpp`
  * Target: `CppInterviewSystemQt`
* The IELTS simulator currently uses CLI-only orchestration:
  * Entry: `src/main_ielts.cpp`
  * Backend modules: `src/ielts/*`, `include/ielts/*`
  * Modes already exist conceptually: full exam, P1 only, P2 only, P3 only, report viewing.
* Existing dirty/untracked local files unrelated to this UI task include `.agents/`, `.cursor/`, `.firecrawl/`, `reports/`, and `test_pa_read*`.
* User confirmed Web is the preferred direction because it can be shared from a blog as a simple link.

## Assumptions

* The existing IELTS CLI should remain available.
* The Web UI should not depend on the old Qt interview UI.
* The first Web version can use browser microphone APIs and call a lightweight local or hosted backend for scoring/generation.
* To move quickly, the MVP can initially run as a local web app before being deployed publicly.

## Requirements

### R1 — IELTS Home Screen

* Show a dedicated IELTS Speaking Simulator home screen in the browser, not the old C++ interview layout.
* Provide clear entry points:
  * Full Mock Exam
  * Practice Part 1
  * Practice Part 2
  * Practice Part 3
  * Reports / History
  * Settings

### R2 — Part-Specific Practice Views

* P1 view:
  * Shows topic/question list progression.
  * Displays current question, answer transcript, follow-up question, and score/feedback.
* P2 view:
  * Shows cue card with title, bullet points, and rounding sentence.
  * Has an explicit ready/start preparation control.
  * Shows preparation countdown and speaking timer.
  * Captures microphone audio in-browser when available.
  * Shows transcript when available and manual transcript fallback when not.
* P3 view:
  * Shows generated discussion questions.
  * Shows candidate answers, follow-ups, and score/feedback.

### R3 — Full Mock Exam Flow

* Supports a complete P1 -> P2 -> P3 run from the UI.
* Shows current part, progress, timer/status, and final report.
* Allows stopping/canceling a run without crashing the realtime/audio client.

### R4 — Reports

* UI can show the latest IELTS JSON report in readable sections:
  * per-part score
  * overall band
  * feedback
  * transcript
* It is acceptable for MVP to show reports generated in the current app session first; persistent report browser can be follow-up if needed.
* Practice pages should initially show a compact score card only:
  * bands
  * short comprehensive feedback
  * backend/source/confidence labels
* A separate detail report view should show:
  * "📊 各维度评分" with Fluency & Coherence, Lexical Resource, Grammatical Range & Accuracy, and pronunciation limitation notes
  * cleaned transcript that removes obvious OCR/STT artifacts without changing the user's content
  * Band 7 spoken-version rewrite preserving the user's core ideas
  * "🔍 升级了哪些地方" comparison table explaining the improvements

### R5 — Visual Redesign

* UI should be fully redesigned around IELTS practice, not technical interview branding.
* Visual style should be quiet, focused, and modern:
  * clear left navigation or top mode switcher
  * strong timer/status area
  * readable question and transcript panes
  * restrained colors with good contrast
  * no marketing hero page
* Avoid nested card-heavy layouts; use structured panes and sections suitable for repeated practice.

### R6 — Web Distribution

* The app should be deployable as a URL that can be linked from a blog.
* Public page should open directly into the practice experience, not a marketing landing page.
* MVP can gate live scoring/generation behind configured backend credentials, but the UI should still allow demo mode/sample questions without secrets in the browser.

### R7 — Backend Boundary

* Do not put API keys or scorer prompts directly into public frontend code.
* Browser UI should call a backend boundary for:
  * scoring
  * P3 question/follow-up generation
  * optional speech-to-text if browser STT is insufficient
* The C++ CLI can remain as the local/reference implementation, but the Web path should define clean request/response contracts so it can be hosted later.

### R8 — Build / Preservation

* Existing CLI target `IELTSSpeakingSimulator` must continue to build.
* Existing Qt interview target `CppInterviewSystemQt` should not be broken.
* Existing Qt code should not be used as the primary IELTS UI implementation.

### R9 — P1/P3 Timed Speaking Flow

* P1 should support an exam-like flow:
  * show question
  * 3-second preparation countdown
  * auto-start recording/dictation/transcript capture
  * fixed answer duration with early stop button
* P3 should support an exam-like flow:
  * show generated discussion question
  * 7-second preparation countdown
  * auto-start recording/dictation/transcript capture
  * fixed answer duration with early stop button
* Transcript source must be explicit: typed, OCR, browser dictation, STT, or unknown.
* Browser/OCR/manual transcript fallback is acceptable, but the UI must label it clearly so users do not mistake OCR text scoring for true audio pronunciation assessment.

## Acceptance Criteria

* [ ] A user can open a Web UI in the browser.
* [ ] UI provides buttons/tabs for Full Exam, P1, P2, P3, Reports, and Settings.
* [ ] P2 UI shows cue card, waits for user start, then shows countdown/timer.
* [ ] P1 shows a 3-second preparation countdown and then starts the speaking window.
* [ ] P3 shows a 7-second preparation countdown and then starts the speaking window.
* [ ] P1/P2/P3 can be started from the Web UI without relying on terminal menu input.
* [ ] UI can display score/feedback/report output.
* [ ] Practice pages show compact score first, and detailed feedback only after opening the detail report.
* [ ] Detailed report includes criterion diagnosis, cleaned transcript, Band 7 rewrite, and upgrade notes.
* [ ] The app has a deployment path suitable for linking from a blog.
* [ ] `IELTSSpeakingSimulator` CLI still builds and `--help` works.
* [ ] Existing `CppInterviewSystemQt` still builds.
* [ ] CTest remains green.

## Open Questions

* Which backend should the first Web UI call: a lightweight local HTTP service wrapping the existing C++/CLI behavior, or a new web-native backend that reimplements scoring/generation endpoints?
* Should the first public demo include live microphone recording, or should it launch with manual transcript input plus browser recording as a follow-up?
* Hosting target is not chosen yet.

## Platform Analysis

### Qt Desktop Strengths

* Best fit for the current C++ codebase: existing Qt target, CMake wiring, PortAudio, RealtimeClient, Config, and reports can be reused directly.
* Good for local microphone workflows and low-level audio/debugging.
* Fastest path to a polished local IELTS practice app without adding a new frontend stack.
* Works offline-ish for UI/report browsing, with realtime/scoring falling back when services fail.

### Qt Desktop Weaknesses

* Poor propagation: users must download/build/install a desktop app.
* macOS signing/notarization, Windows packaging, updates, and permissions add operational overhead.
* Harder to share a practice link, teacher feedback session, public demo, or hosted report.
* UI iteration is slower than web for modern visual polish and product experiments.

### Recommended Product Direction

* Web is now the primary direction because the user wants link-based sharing from a blog.
* Keep Qt as an internal/local option only.
* Avoid deeply coupling IELTS business logic to Qt widgets or terminal IO. The Web UI should call a clear application/backend boundary so the same IELTS behavior can be hosted and shared.

## Recommended MVP Shape

* Frontend: browser app with mode navigation for Full/P1/P2/P3/Reports/Settings.
* Backend boundary:
  * `GET /api/question-bank/summary`
  * `POST /api/session/start`
  * `POST /api/score`
  * `POST /api/p3/questions`
  * `POST /api/p3/follow-up`
* MVP input:
  * P1/P3: browser transcript text area plus optional speech capture.
  * P2: cue card, preparation timer, speaking timer, transcript text area; browser recording can be added if feasible.
* Deployment:
  * frontend can be linked from a blog;
  * backend credentials stay server-side.

## Out of Scope

* Web UI.
* Mobile UI.
* Replacing the existing original C++ interview UI.
* Full report analytics dashboard beyond readable report display.
* Pixel-perfect design system unless needed after MVP.

## Technical Notes

* Existing Qt UI uses `QMainWindow`, `QTextEdit`, `QPushButton`, `QProgressBar`, menu/toolbar, and stylesheet-based styling.
* Existing Qt UI is coupled to `interview::session::DialogSession`; IELTS UI should avoid that coupling and use IELTS-specific orchestration.
* Current CLI loop in `src/main_ielts.cpp` contains the mode menu that can guide UI navigation.
* Scoring prompt/product issues are tracked in `docs/IELTS_SCORING_ISSUES_AND_PROMPT_PLAN.md`; do not treat current flat IELTS band output as final product behavior.
* IELTS backend currently expects blocking terminal flows in some places, so the UI implementation likely needs either:
  * a worker-thread wrapper around existing sessions for MVP, or
  * a refactor to expose non-terminal/event-driven session steps.
