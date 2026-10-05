# System appearance and native C++ voice architecture audit

## Goal
Continue the Qt desktop handoff: implement the explicitly requested system appearance option and produce an evidence-based native C++ low-latency speech design suited to interview discussion and later implementation.

## Requirements
- Appearance has light, dark, and follow-system choices in web and desktop, persists the selected preference, reacts to live system changes only in system mode, and preserves legacy manual selections without a first-paint flash.
- Audit the original C++ prototype with concrete file/line evidence for callback safety, buffer bounds, concurrency, cancellation, protocol correctness, and existing integration/tests.
- Compare mature open-source audio/transport components against Qt alternatives using current primary documentation. C++ ownership and measurable performance matter more than minimizing dependencies.
- Check current Volcengine realtime authentication and whether temporary credentials are documented; do not equate a bearer token with short-lived scoped credentials or silently distribute a server key.
- Recommend interview backend placement based on existing speaking/report architecture.
- Update the copyable handoff with user decisions and research/implementation status.
- Work on local ui-polish; do not push or commit backend_django/db.sqlite3.

## Acceptance Criteria
- [x] Three appearance choices work with legacy preference migration and live system updates.
- [x] Appropriate existing checks and behavior verification pass.
- [x] C++ audit and component/authentication research saved under research/ with sources and uncertainty.
- [x] Handoff includes latency measurement stages, reasonable experimental targets, backend recommendation, and VPS deferred until local validation.
- [x] Focused changes reviewed; user approved the two local commits, excluding the existing database modification.

## Scope and assumptions
User explicitly approved appearance implementation. Voice architecture is under evaluation: this turn delivers a concrete proposed plan and evidence, not a speculative full voice rewrite. Later mode-switcher/mock-interview phases retain their own design review.
Future extension: standalone C++ engine behind Qt/QWebChannel adapter, interchangeable device/transport backends, separate interview domain over shared AI/media/report infrastructure.
Edge cases: invalid/missing storage, denied storage, live OS appearance changes, microphone device changes, network backpressure, stale audio after interruption, auth expiry.

## Out of scope
Buying/deploying a VPS, publishing, UI mode switcher, full mock interview feature, new voice engine implementation, claims of superior industrial performance without comparable benchmarks.

## Research References
- research/cpp-voice-audit.md — original prototype and backend reuse review.
- research/native-voice-components.md — current component choices and realtime authentication.

## Technical Notes
- docs/reports/qt-desktop-mock-interview-handoff-2026-10-05.md
- docs/superpowers/specs/2026-10-05-qt-desktop-studio-design.md
- web/static/appearance.js, web/static/index.html, web/static/app.js
- Existing backend_django/db.sqlite3 is dirty before this task.

## Verification record
- JavaScript: full suite 66/68; two obsolete stylesheet-version assertions fixed and their focused reruns 2/2. All 68 files accounted for.
- Desktop shell: ctest 3/3, no native voice target exists yet.
- Syntax and diff checks passed. Desktop account appearance control visually checked; actual OS theme switching not manually tested.
- No microphone/provider benchmarks or voice code implementation this turn.

## Commit authorization
User explicitly approved two local ui-polish commits. Appearance commit: 0c31323. This documentation commit includes the audit, plan, updated handoff and task context. No push; existing database excluded.
