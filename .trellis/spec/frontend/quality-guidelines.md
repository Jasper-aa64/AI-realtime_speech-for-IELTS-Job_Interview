# Quality Guidelines

> Code quality standards for frontend development.

---

## Overview

Frontend work in this project currently includes a native Qt interface for the
original interview product and a Web-first IELTS practice UI under `web/`.
The IELTS Web UI is the distribution-oriented surface: it must be shareable by
link, avoid browser-side secrets, and keep practice workflows usable when
server-side CLI integrations are unavailable.

## Scenario: IELTS Web UI

### 1. Scope / Trigger

- Trigger: Browser UI for IELTS Speaking practice that can be linked from a
  blog and backed by server-side CLI integrations.
- Scope: `web/static/*`, `web/ielts_server.py`, API tests under `tests/`, and
  documentation in `README.md`.

### 2. Signatures

- Local server:
  ```bash
  python3 web/ielts_server.py --host 127.0.0.1 --port 8765 --data-dir data/ielts --reports-dir reports
  ```
- Browser entry:
  ```text
  http://127.0.0.1:8765/
  ```
- API boundary:
  ```text
  GET  /api/question-bank/summary
  POST /api/question-bank/sample
  POST /api/session/start
  POST /api/score
  POST /api/p3/questions
  POST /api/p3/follow-up
  POST /api/attempts/start
  POST /api/attempts/{id}/turns/{turn_id}/audio
  POST /api/attempts/{id}/turns/{turn_id}/complete
  POST /api/attempts/{id}/score
  POST /api/attempts/{id}/abort
  GET  /api/history
  GET  /api/history/{id}
  POST /api/tts
  ```

### 3. Contracts

- Frontend code must not contain API keys, CLI tokens, model credentials, or
  hidden prompt secrets.
- Scoring and P3 generation must go through backend endpoints. The backend may
  use local `codex`/`claude` CLI tools or deterministic fallbacks.
- The UI must expose `Mock`, `P1`, `P2`, `P3`, `History`, and `Settings`
  navigation.
- The formal practice UI is voice-first: do not expose a textarea answer entry.
  Browser dictation is only an automatic transcript source.
- Practice state is `idle`, `examiner_playing`, `preparing`, `recording`,
  `processing`/`scoring`, `summary`, or aborted/reset.
- P1/P3 play the examiner question automatically after the learner starts a
  section; P2 plays instruction-only audio and shows the cue card for reading.
- Every active attempt needs an `Exit` control. Exit must stop examiner audio,
  browser `speechSynthesis`, timers, pending next-turn timeouts, dictation,
  MediaRecorder, and media tracks, then call the abort endpoint.
- History is a horizontally scrollable `Recent attempts` rail with visible
  affordance and active item state; details render full width below it.
- Details should render a per-turn table with columns: `题目`, `Your recording`,
  `Band 7 spoken version`, and `升级了什么`.

### 4. Validation & Error Matrix

- API response is not JSON -> show a clear frontend error instead of crashing.
- API returns non-2xx -> surface the backend error message.
- Claude/Codex unavailable -> backend returns fallback content/score where
  practice can continue.
- Question bank unavailable or malformed -> backend returns a JSON error with a
  non-2xx status.
- Exit/cancel during any phase -> all timers/audio/recording/pending async UI
  continuations are stopped or guarded; no report is shown.
- Missing browser transcript with uploaded audio -> show a transcript-missing
  status and keep the recording playable.

### 5. Good/Base/Bad Cases

- Good: The Web UI can be opened from a blog link while credentials remain
  server-side.
- Base: Browser dictation is unavailable; the user can still record audio, and
  the report marks transcript as missing/incomplete rather than inventing text.
- Bad: The frontend directly shells out to CLI tools or embeds API keys.

### 6. Tests Required

- `node --check web/static/app.js`
- `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py`
- `python3 -m unittest discover -s tests -p 'test_*.py'`
- HTTP smoke checks for `/`, API summary, session start, score, and P3
  generation.
- Existing C++ CLI/Qt build checks and `ctest` must remain green.

### 7. Wrong vs Correct

#### Wrong

```js
const apiKey = "sk-...";
fetch("https://api.example.com/score", { body: transcript });
```

#### Correct

```js
await api("/api/score", {
  method: "POST",
  body: JSON.stringify({ transcript, part: "part2" })
});
```

---

## Forbidden Patterns

- Do not put secrets, local CLI paths, or model credentials in browser code.
- Do not make the IELTS Web UI depend on the old Qt interview widgets.
- Do not render reports only as raw JSON when structured fields are available.
- Do not let timers, speech synthesis, audio playback, MediaRecorder, or
  delayed next-turn callbacks continue after Exit or navigation.
- Do not render a formal textarea answer entry in the practice UI.

---

## Required Patterns

- Route model/scoring/generation operations through backend endpoints.
- Provide deterministic fallback behavior for demo/practice flows.
- Keep mode navigation explicit: Mock, P1, P2, P3, History, Settings.
- Keep P2 layout stable after start: cue card fixed at top and recorder position
  unchanged while Listening/Preparing/Recording/Saving changes state.
- Guard late async continuations after abort so save/score responses cannot
  resurrect the old attempt UI.
- Use defensive API parsing in the frontend; assume errors may be non-JSON or
  malformed.
- Use an id-aware DOM helper for the IELTS web UI: if a helper like `$()`
  accepts a bare token, it must resolve ids via `getElementById()` before
  falling back to `querySelector()`.
- Treat critical runtime bindings in `bindEvents()` as optional-safe when the
  target node may be missing in a partial render, so a single absent control
  does not prevent the rest of the page from initializing.
- Keep dark tone navigation readable: if a tone is intentionally near-black
  (for example Mock), increase contrast with text and borders so it remains
  legible against the black sidebar.
- Replace placeholder or garbled initial status text with a natural sentence
  before shipping; visible `????` / broken fallback text is a release blocker.
- Settings and report-side guidance for Chinese learners should use natural
  Chinese labels, not literal English placeholders. If weak-question training
  is shown, surface the weak reason and the next review time rather than only
  a count.

---

## Testing Requirements

- Web UI changes require JS syntax checks and backend API tests.
- Backend boundary changes require HTTP-level tests for success and error
  responses.
- Changes must not break existing C++ CLI/Qt targets or CTest.

---

## Code Review Checklist

- Are secrets kept out of `web/static/*`?
- Does each user-visible mode have a clear start/reset path?
- Are API failures visible and understandable to the learner?
- Are reports readable without opening raw JSON?
- Is the app still shareable as a simple URL?
- Can the learner exit without further automatic sound playback?
- Do P1/P3/P2 reports show per-turn recording, transcript status, Band 7
  version, and upgrade notes?
