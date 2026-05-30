# Quality Guidelines

> Code quality standards for frontend development.

---

## Overview

Frontend work in this project now treats `web/static/` as the production SPA
surface served by Django. The retired `web/ielts_server.py` is not a production
runtime. The UI must remain shareable by link, avoid browser-side secrets, and
keep practice workflows usable when server-side AI/TTS integrations are
unavailable.

## Scenario: IELTS Web UI

### 1. Scope / Trigger

- Trigger: Browser UI for IELTS Speaking practice that can be linked from a
  blog and backed by server-side CLI integrations.
- Scope: `web/static/*`, Django `/api/*` contracts, and runtime documentation.

### 2. Signatures

- Local server:
  ```bash
  python backend_django/manage.py runserver 127.0.0.1:8767 --noreload
  ```
- Browser entry:
  ```text
  http://127.0.0.1:8767/
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
- Scoring and P3 generation must go through Django backend endpoints. The
  backend may use local AI providers or explicit fallbacks.
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
- `python backend_django/manage.py check`
- Targeted Django tests for touched apps.
- `python scripts/validate_legacy_server_retirement.py` when runtime docs,
  launch scripts, or legacy server boundaries change.
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
- Do not make the IELTS Web UI depend on the old Qt interview widgets or the
  retired `web/ielts_server.py` runtime.
- Do not render reports only as raw JSON when structured fields are available.
- Do not let timers, speech synthesis, audio playback, MediaRecorder, or
  delayed next-turn callbacks continue after Exit or navigation.
- Do not render a formal textarea answer entry in the practice UI.

---

## Required Patterns

- Route model/scoring/generation operations through backend endpoints.
- Keep all frontend network traffic on the Django `/api/*` surface.
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
- Scrollable card grids such as P1/P2 corpus libraries must size rows from
  content, e.g. `grid-auto-rows: max-content`, instead of forcing equal-height
  tracks inside a constrained scroll region. Otherwise populated cards can
  collapse into thin bars when the grid has many rows and `overflow` is hidden.
- Writing prompt highlight deletion must be driven by the highlight index and
  pointer coordinates captured on `pointerdown`. A click on an existing
  highlight may produce selection/range churn before `pointerup`, and
  `event.target` can be unreliable after DOM selection changes. Do not require
  an empty selection before opening the Delete menu, and stop propagation inside
  the menu so outside-click handlers cannot close it immediately.
- Speaking turn completion should not block the next pre-existing question
  after the answer audio upload succeeds. Keep `/turns/{id}/complete` in the
  background for ordinary turns, then wait for pending completions before final
  scoring. Only keep completion synchronous when the next prompt depends on the
  just-recorded answer, such as P1 work/study identity follow-up insertion, P3
  adaptive follow-up generation, or the final turn before scoring.

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

## Scenario: Django Writing Score Task Bridge

### 1. Scope / Trigger

- Trigger: The vanilla Web writing UI submits AI writing scoring through the
  Django durable `writing_score` task flow while the old web server still owns
  the browser origin.
- Scope: `web/static/app.js`, `web/static/styles.css`, old-server proxy routes
  in `web/ielts_server.py`, Django writing/AI task APIs, and writing report UI.

### 2. Signatures

- Save entry:
  ```text
  POST /api/writing/entries
  ```
- Create or reuse durable score task:
  ```text
  POST /api/writing/entries/{entry_id}/score-task
  ```
- Poll refresh-safe entry detail:
  ```text
  GET /api/writing/entries/{entry_id}
  ```
- Optional pending cancellation:
  ```text
  POST /api/ai/tasks/{task_id}/cancel/
  ```
- Local worker boundary:
  ```text
  python backend_django/manage.py run_ai_tasks --limit N
  ```

### 3. Contracts

- The frontend saves the entry before scoring and treats `entry.id` as the
  durable polling key.
- `score-task` returns `{created, task, entry}`; duplicate submissions for the
  same answer hash should reuse the existing task.
- Entry detail is the UI recovery surface and must include `score` plus the
  latest `ai_task` when one exists.
- Active task statuses are `pending` and `running`; terminal statuses are
  `succeeded`, `fallback`, `failed`, and `cancelled`.
- The old web server may proxy `/api/writing/*` and `/api/ai/tasks/*` to
  Django when a Django `sessionid` cookie is present. Without Django proxy
  support, the frontend may fall back to the old synchronous `/score` endpoint.

### 4. Validation & Error Matrix

- `score-task` returns legacy `404 Unknown API endpoint` -> frontend may fall
  back to `POST /api/writing/entries/{entry_id}/score`.
- `score-task` returns any other 4xx/5xx -> show the backend error; do not hide
  billing, auth, or validation failures behind synchronous fallback.
- Entry detail has `ai_task.status=pending|running` -> show a visible waiting
  state and keep polling by entry id.
- Entry detail has `score` or `ai_task.status=fallback|succeeded` -> render the
  writing report from persisted entry detail.
- Entry detail has `ai_task.status=cancelled` with no score -> keep the entry
  saved and unscored; do not invent AI feedback.
- Entry detail has `ai_task.status=failed` with no score -> show failure status
  and allow the user to retry later.

### 5. Good/Base/Bad Cases

- Good: A logged-in user submits scoring, refreshes during `pending`, and the
  UI recovers by polling `GET /api/writing/entries/{entry_id}` until the
  worker persists fallback or success.
- Base: Django is unavailable for writing, the old JSON writing endpoint still
  saves and scores through the synchronous fallback path.
- Bad: The browser keeps only an in-memory promise for scoring and loses the
  report after refresh or navigation.
- Bad: A non-legacy API error from `score-task` silently falls back to sync
  scoring and masks billing/auth problems.

### 6. Tests Required

- `node --check web/static/app.js`.
- `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py`.
- Old Web tests proving `/api/writing/entries/{id}/score-task` and
  `/api/ai/tasks/{task_id}/cancel/` proxy to Django with a `sessionid` cookie.
- Django tests covering writing score task creation, polling payload, pending
  cancellation, running cancellation conflict, fallback/success persistence,
  and learner profile updates.
- Browser smoke check for logged-in save -> score-task pending wait -> worker
  fallback/success -> writing report render.

### 7. Wrong vs Correct

#### Wrong

```js
const scored = await api(`/api/writing/entries/${entry.id}/score`, {});
state.writing.entry = scored;
```

This blocks the browser flow on synchronous scoring and loses the durable task
boundary needed for refresh recovery.

#### Correct

```js
const result = await api(`/api/writing/entries/${entry.id}/score-task`, {});
startWritingScorePolling(result.entry.id);
```

Polling entry detail keeps Django as the source of truth and lets worker
completion append the result to the user's writing record.

## Scenario: Writing Report Revision Editing

### 1. Scope / Trigger

- Trigger: A user opens an existing writing report and chooses either `继续编辑` for an unscored draft or `修改作文并重新生成报告` for a scored report.
- Scope: `web/static/app.js`, Django writing entry APIs, and writing report list ordering.
- Cross-layer contract: editing an unscored report continues the same entry; editing a scored report with an existing `WritingScore` creates a new draft revision and never mutates the scored source entry.

### 2. Signatures

- Clone a report entry for revision:
  ```text
  POST /api/writing/entries/{entry_id}/clone
  ```
- Load a cloned draft directly in the editor:
  ```text
  GET /?view=writing&task={task_type}&prompt={prompt_id}&writing_entry={clone_entry_id}
  ```
- Continue editing an unscored entry directly:
  ```text
  GET /?view=writing&task={task_type}&prompt={prompt_id}&writing_entry={source_entry_id}
  ```
- Existing fallback/read surfaces:
  ```text
  GET  /api/writing/entries/{entry_id}
  POST /api/writing/entries
  ```

### 3. Contracts

- An entry is treated as scored only when `entry.status === "scored"` and a persisted `WritingScore` exists.
- For an unscored entry, normal click switches the current tab to the writing editor and calls `recoverWritingEntry(sourceEntry)`; it must not call `/clone` or create another draft.
- For an unscored entry, Command/Ctrl/middle-click opens `writingEntryEditUrl(sourceEntry)` directly in the new tab.
- For a scored entry, normal click clones the source entry, then switches the current tab to the writing editor and calls `recoverWritingEntry(clone)`.
- For a scored entry, Command/Ctrl/middle-click opens a blank tab synchronously, clones the source entry, then redirects that tab to `writingEntryEditUrl(clone)`.
- The cloned entry must copy `task_type`, `prompt_id`, `prompt`, `title`, `category`, `image_url`, `answer`, and `prompt_highlights`.
- The source scored entry keeps its existing `WritingScore`; the clone starts as `saved` with no `score`.
- The UI must not clear `state.writing.prompt`, `state.writing.entry`, or the answer textarea before a valid clone exists.

### 4. Validation & Error Matrix

- Unscored source entry -> continue editing the source entry; no `/clone` request is made.
- Clone succeeds -> load cloned prompt and answer into the editor; old report remains visible in reports.
- Clone requested for unscored or `status=scored` without `WritingScore` -> backend rejects it; frontend should not normally reach this path.
- Clone endpoint returns legacy route `404` but source entry `GET` succeeds -> create a new saved draft through `POST /api/writing/entries`.
- Clone endpoint returns missing-source `404` -> stay on the report page and show an inline error; do not blank the editor.
- Popup blocked on modifier-click -> show an error telling the user to allow popups or use normal click.
- Duplicate rapid clicks while clone is pending -> ignore additional clicks to avoid duplicate drafts.

### 5. Good/Base/Bad Cases

- Good: The user edits a Band 5.5 report, gets a new unscored draft to the left of the old report, and the old Band 5.5 report is still available.
- Good: The user opens an unscored saved draft from reports, sees `继续编辑`, and returns to the same prompt and answer without a duplicate report card.
- Base: Legacy server lacks `/clone`; frontend reads the source entry and saves a new draft without touching the source score.
- Bad: The frontend opens the writing page and clears the prompt/textarea before clone completes.
- Bad: Autosave writes edited text back into the scored source entry and deletes the original `WritingScore`.
- Bad: A saved unscored draft is cloned into another unscored draft when the user only wanted to continue editing.

### 6. Tests Required

- `node --check web/static/app.js`.
- Django tests proving `POST /api/writing/entries/{entry_id}/clone` returns a saved clone with no score and preserves the source `WritingScore`.
- Django tests proving `POST /api/writing/entries/{entry_id}/clone` rejects unscored entries and `status=scored` entries without `WritingScore`.
- Django tests proving `POST /api/writing/entries` with a changed scored entry creates a revision instead of deleting the old score.
- Browser smoke for normal click and Command/Ctrl-click from both an unscored writing report and a scored writing report.

### 7. Wrong vs Correct

#### Wrong

```js
state.writing.prompt = null;
state.writing.entry = null;
switchView("writing");
const clone = await cloneWritingEntryForRevision(entryId);
```

This can leave the editor empty if cloning fails or if `loadWriting()` races into default prompt loading.

#### Correct

```js
const clone = await cloneWritingEntryForRevision(entryId);
switchView("writing", { force: true });
await recoverWritingEntry(clone);
```

Clone first, then navigate and recover the cloned prompt and answer.

## Scenario: Writing Prompt Highlight Delete Menu

### 1. Scope / Trigger

- Trigger: A user clicks an existing highlighted phrase inside the writing prompt and wants to remove that highlight.
- Scope: `web/static/app.js` prompt highlight event handling and `web/static/styles.css` highlight menu styling.
- Contract: text selection creates highlights; clicking an existing highlight opens a stable delete menu near the pointer.

### 2. Signatures

- Prompt highlight state is stored on the writing entry payload:
  ```json
  { "prompt_highlights": [{ "start": 46, "end": 127 }] }
  ```
- Delete menu target state:
  ```js
  state.writing.pendingHighlightDeleteIndex
  ```

### 3. Contracts

- Dragging/selecting plain prompt text must not show `Delete`; it may show the highlight action.
- Clicking an existing `.writing-highlight-mark` opens `writingHighlightMenu` in delete mode near the pointer/click anchor.
- The same pointer/click/selectionchange event sequence that opened the menu must not immediately close it.
- Pointer events inside the menu must not bubble into outside-close handlers.
- `Enter` or `Space` on a focused highlight mark must open the same delete menu.
- Delete removes the selected highlight immediately without a confirmation dialog.

### 4. Validation & Error Matrix

- Click existing highlight -> menu stays visible until the user clicks Delete, clicks outside, presses Esc, or navigates away.
- Click Delete -> remove the indexed range immediately and persist `prompt_highlights`.
- Drag select text across highlight -> treat as text selection, not as delete intent.
- Stale or invalid highlight index -> close safely and do not mutate highlight state.

### 5. Good/Base/Bad Cases

- Good: User clicks highlighted text, the compact Delete menu appears beside the cursor, and the user can move to it and delete.
- Base: Keyboard user tabs to a highlight and presses `Enter`; the Delete menu appears with visible focus.
- Bad: The menu appears while selecting ordinary text.
- Bad: The menu opens and disappears on the same mouseup/selectionchange before the user can click it.
- Bad: The menu is a large bright danger block that covers the prompt text.

### 6. Tests Required

- `node --check web/static/app.js`.
- `git diff --check`.
- Browser smoke: create a prompt highlight, click the highlighted range, verify Delete remains visible near the pointer, click Delete, and verify the highlight is removed without a confirmation dialog.
- Browser smoke: drag select prompt text and verify Delete does not appear.

### 7. Wrong vs Correct

#### Wrong

```js
promptEl.addEventListener("pointerdown", () => hideWritingHighlightMenu());
document.addEventListener("selectionchange", hideWritingHighlightMenu);
```

This closes the menu during the same click sequence that is supposed to open it.

#### Correct

```js
if (event.target.closest(".writing-highlight-mark")) {
  openWritingPromptHighlightDeleteMenu(index, { clientX: event.clientX, clientY: event.clientY });
}
```

Treat highlight clicks as object actions, and keep outside-close logic from consuming menu-internal pointer events.
