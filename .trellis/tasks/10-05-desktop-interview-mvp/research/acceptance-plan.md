# Acceptance plan and unattended defaults

The user's 2026-10-05 instruction permits recommended defaults without further questions during their absence. This supersedes old handoff steps that asked to approve each design phase. Separate interview app in the same Django service is adopted; mature audio adapters wrap a Qt-independent C++ engine. Hardware/backend selection remains empirical.

## Safe verification environment
- New SQLite database in the chat work directory, never migrate or test against the existing dirty database.
- New localhost 8768 QA server, independent of already running 8767 server. Existing public tunnel and AI worker stay untouched.
- Synthetic local QA account; no real resume, paid provider call or hardware microphone capture.
- Off-record Qt --test-profile for GUI QA, preserving the default persistent login profile.

## User-visible scenarios
1. Regular browser has no interview switcher. Desktop discovers the native capability bridge and offers IELTS/interview modes.
2. Switching works by pointer and keyboard; Escape/outside closes; preference survives normal desktop reload; reduced motion has no spatial animation.
3. Bank category selection, create three-question practice, type an answer, save, skip next, resume/reload, finish, inspect durable transcript in history.
4. Custom resume text/PDF+JD submission validates missing/oversized/unreadable content. Unconfigured AI is visible; local question practice keeps working. Configured success proven with fixtures, never disguised fallback.
5. AI follow-up cannot duplicate or reorder already answered turns. Provider failures leave session progress unchanged and retryable.
6. Feedback clearly uses text only. No IELTS bands or fabricated pronunciation/voice assessment.
7. Login/logout and account changes do not leak previous user's session, drafts or resume between accounts.
8. Browser iframe/foreign-origin navigation cannot obtain native bridge functionality.

## Native engine scenarios
SPSC wraparound, bounded pressure, arbitrary callback sizes, explicit overflow policy, render silence on underrun, epoch-based stale drop, interrupt while queued, shutdown under load, repeated start/stop, callback quiescence before storage reset. Sanitizers where platform permits; synthetic benchmark records count and P50/P95/P99, keeping physical/DAC/provider delay unmeasured.

## Evidence to publish
Tests and compiler results, synthetic benchmark caveats, screenshot if computer-use surfaces become available, precise remaining live-provider/hardware integration work. Never label typed practice as native realtime voice completion.
