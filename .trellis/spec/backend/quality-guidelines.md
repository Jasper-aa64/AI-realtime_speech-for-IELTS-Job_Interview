# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

Backend changes must preserve independent build targets and keep feature
contracts testable through CMake/CTest. When a feature crosses data files,
external command-line tools, reports, and runtime services, document and test
the boundary behavior instead of relying only on manual end-to-end runs.

## Scenario: IELTS Speaking CLI Simulator

### 1. Scope / Trigger

- Trigger: This feature adds a new executable, runtime data contracts, external
  CLI integrations, and generated JSON reports.
- Scope: `IELTSSpeakingSimulator`, `src/ielts/`, `include/ielts/`,
  `data/ielts/`, `reports/ielts_*.json`, and CMake/CTest wiring.

### 2. Signatures

- Build target: `IELTSSpeakingSimulator`
- Smoke test target: `ielts_data_test`
- CLI entry:
  ```bash
  ./IELTSSpeakingSimulator [--data-dir data/ielts] [--reports-dir reports] [--config config/default_config.json]
  ./IELTSSpeakingSimulator --help
  ```
- Question bank:
  ```cpp
  void QuestionBank::LoadPart1(const std::string& data_dir);
  void QuestionBank::LoadPart2(const std::string& data_dir);
  std::vector<P1Question> QuestionBank::SampleP1Questions(int n = 5) const;
  P2Topic QuestionBank::SampleP2Topic() const;
  ```
- Scoring:
  ```cpp
  IELTSScore Scorer::Score(const std::string& transcript);
  ```
- Realtime capture:
  ```cpp
  bool interview::services::RealtimeClient::IsConnected() const;

  RealtimeCaptureResult CaptureSpeechWithRealtime(
      interview::services::RealtimeClient& rt_client,
      const RealtimeCaptureOptions& options);
  ```

### 3. Contracts

- Part 1 files live under `data/ielts/part1/*.json`:
  ```json
  {
    "season": "2025-autumn",
    "part": 1,
    "topic": "family",
    "questions": ["Do you live with your family?"]
  }
  ```
- Part 2 files live under `data/ielts/part2/*.json`:
  ```json
  {
    "season": "2025-autumn",
    "part": 2,
    "topics": [
      {
        "title": "Describe a book you recently read",
        "bullets": ["What it was about"],
        "p3_theme": "reading_habits"
      }
    ]
  }
  ```
- Prompt files are required:
  - `data/ielts/prompts/scorer_system.md`
  - `data/ielts/prompts/p3_question_gen.md`
- Reports are written as `reports/ielts_YYYYMMDD_HHMMSS.json` and include:
  `timestamp`, `candidate`, `parts`, `overall.band`, and per-part transcript
  and score objects when that part was run.
- Overall IELTS band is recomputed locally from the four scoring dimensions and
  rounded upward to the next 0.5. Do not trust a model-provided overall value.
- P1/P2 speech capture should use realtime STT when `RealtimeClient` is
  connected. If realtime is disconnected, send fails, or no transcript returns,
  the CLI must keep the exam usable through terminal transcript fallback.
- P2 must keep recording microphone samples for WAV output even when realtime
  STT is unavailable, as long as the local audio device can be opened.
- `RealtimeClient::SetResponseCallback()` may be called after `Connect()`.
  Implementations must start the receive thread exactly once and must not
  restart over a joinable thread. If the receive loop ends or fails, connection
  state must be reset so upper layers can choose fallback behavior.

### 4. Validation & Error Matrix

- Missing `data/ielts/part1` or `part2` directory -> throw a runtime error with
  the missing path.
- Malformed JSON -> throw a runtime error naming the file.
- Part 1 file with non-array `questions` -> throw a runtime error.
- Part 2 file with non-array `topics` -> throw a runtime error.
- Empty loaded Part 1 or Part 2 bank -> throw a runtime error before the exam
  starts.
- Codex/Claude CLI unavailable, non-zero, or empty output -> log the failure and
  use deterministic fallback scoring/questions where the session can continue.
- Realtime disconnected before capture -> return a fallback reason and do not
  attempt STT audio sends.
- Realtime send failure during capture -> continue local recording, log a
  warning, and return a fallback reason.
- Realtime returns no final/interim transcript -> fall back to terminal input
  for P1/P2 transcript text.
- Realtime receive-loop failure/session end -> mark the client disconnected.
- Report or WAV write failure -> throw a runtime error; do not silently ignore
  failed output writes.

### 5. Good/Base/Bad Cases

- Good: A new `data/ielts/part1/YYYY_season_topic.json` file is added; no code
  changes are needed and the next run can sample it.
- Base: `IELTSSpeakingSimulator --help` works without connecting to realtime
  services.
- Base: Realtime connection fails at startup; the IELTS CLI logs the issue and
  continues in transcript fallback mode.
- Bad: A session hardcodes `reports/` instead of using `--reports-dir`; this
  breaks testability and user-selected output locations.
- Bad: `Close()` reads from the websocket while the receive thread is also
  reading; only one receive path may own websocket reads at a time.

### 6. Tests Required

- CMake configure must succeed from a clean build directory.
- `IELTSSpeakingSimulator` target must build.
- `IELTSSpeakingSimulator --help` must exit successfully.
- `ielts_data_test` must load bundled Part 1, Part 2, and prompt files and
  assert non-empty sampled data.
- Realtime capture changes must build both the IELTS target and existing tests,
  because `RealtimeClient` is shared with the original interview flow.
- `ctest --output-on-failure` should pass for the configured build directory.

### 7. Wrong vs Correct

#### Wrong

```cpp
std::ofstream wav("reports/part2.wav");
wav << bytes; // no error check
```

#### Correct

```cpp
std::filesystem::create_directories(reports_dir);
std::ofstream wav(path, std::ios::binary);
if (!wav) {
    throw std::runtime_error("Failed to write IELTS WAV recording: " + path.string());
}
```

---

## Forbidden Patterns

- Do not make terminal-only targets depend on Qt sources or widgets.
- Do not hardcode runtime output paths inside session classes; pass configured
  directories through the manager/session constructor.
- Do not silently ignore failed file writes for reports, recordings, or prompt
  artifacts.
- Do not let LLM-generated JSON scores define `overall_band`; recompute it from
  the validated dimensions.
- Do not let IELTS P1/P2 require live realtime credentials to run; keep terminal
  transcript fallback available.
- Do not introduce competing websocket readers in `RealtimeClient` shutdown.

---

## Required Patterns

- Use CMake targets for buildable units and register smoke tests with CTest.
- Keep data-driven features reloadable through files under `data/` without
  requiring recompilation.
- Shell-out integrations must have a deterministic fallback or a clear runtime
  error, depending on whether the user flow can safely continue.
- Realtime integrations used by CLI flows must expose a connection check and
  route disconnected/no-transcript cases to explicit fallback behavior.

---

## Testing Requirements

- Every new executable target needs at least a build check and a no-service
  smoke path such as `--help`.
- Every bundled runtime data contract needs a test that loads representative
  files and asserts the minimum fields required by the application.

---

## Code Review Checklist

- Does the new target avoid unrelated UI or legacy feature sources?
- Are user-configured paths respected through all layers?
- Are external CLI failures handled explicitly?
- Are JSON file formats validated at load time?
- Can the core target and its smoke/data tests run without live credentials?
- Does realtime capture preserve fallback behavior and avoid regressions to the
  shared interview realtime client?

## Scenario: IELTS Web API Boundary

### 1. Scope / Trigger

- Trigger: The browser UI must be shareable by link while keeping Codex/Claude
  CLI usage and any future credentials server-side.
- Scope: `web/ielts_server.py`, `web/static/*`, `tests/test_ielts_web_server.py`,
  question-bank JSON, reports, and README run/deploy instructions.

### 2. Signatures

```text
GET  /api/question-bank/summary
POST /api/question-bank/sample
POST /api/session/start
POST /api/score
POST /api/p3/questions
POST /api/p3/follow-up
GET  /api/reports/latest
POST /api/attempts/start
POST /api/attempts/{id}/turns/{turn_id}/audio
POST /api/attempts/{id}/turns/{turn_id}/complete
POST /api/attempts/{id}/score
POST /api/attempts/{id}/abort
GET  /api/history
GET  /api/history/{id}
GET  /api/audio/{id}/{turn_id}/candidate
GET  /api/audio/{id}/{turn_id}/examiner
GET  /api/audio/{id}/model
POST /api/tts
```

Local server command:

```bash
python3 web/ielts_server.py --host 127.0.0.1 --port 8765 --data-dir data/ielts --reports-dir reports
```

### 3. Contracts

- Frontend code must never contain API keys, Claude/Codex credentials, or local
  shell commands.
- Server-side scoring may use CLI integrations only when explicitly enabled by
  server environment/config; fallback scoring must keep the demo usable.
- API responses must be JSON for both success and expected error cases.

### IELTS Web Attempt Contract

- Attempts use `status`: `started`, `ready_to_score`, `scored`, or `aborted`.
- `POST /api/attempts/{id}/abort` sets `status=aborted` and `aborted_at`; scored
  attempts cannot be aborted.
- `/api/attempts/{id}/score` must reject aborted attempts and incomplete
  attempts with JSON errors.
- `/api/history`, `/api/history/{id}`, and `latest_report` must use the same
  scored-report gate. A report is valid only when `status == "scored"`,
  `ielts_score.overall_band` is a finite numeric value, there is at least one
  turn, and every turn has `status == "completed"`.
- Started, `ready_to_score`, aborted, malformed scored-looking, or partially
  completed attempts must not appear in history and must not render as report
  detail.
- Each turn must persist:
  `transcript_raw`, `transcript_cleaned`, `transcript_status`,
  `pronunciation`, `band7_version`, `model_audio`, and `upgrade_notes`.
- `transcript_status` is one of `captured`, `interim_fallback`, or `missing`.
  Missing transcript turns may still have playable uploaded audio.
- P2 `examiner_text` is instruction-only and must not include the cue title,
  cue bullets, or `You should say`; the full cue card remains in `turn.question`
  and `attempt.cue_card` for scoring/reporting.
- Band 7 model output must be cleaned before storage. Remove Trellis/session
  bootstrap text, workflow/status logs, Markdown fences, and non-answer
  prefixes; use deterministic fallback when cleaned output is not a plausible
  spoken answer.
- Session start returns the sampled questions/topics needed by the selected
  mode and a `session_id` the UI can pass back to scoring/report endpoints.
- Reports are stored server-side under the configured report directory.

### 4. Validation & Error Matrix

- Unknown endpoint -> `404` JSON error.
- Malformed JSON request -> `400` JSON error.
- Missing transcript on score request -> `400` JSON error.
- Missing/malformed question-bank data -> non-2xx JSON error naming the
  problem.
- Claude/Codex disabled or unavailable -> deterministic fallback response, not
  a frontend crash.

### 5. Good/Base/Bad Cases

- Good: Blog links point to the Web UI while the backend owns all model/scoring
  execution.
- Base: Server runs with no CLI tools enabled and still supports demo practice
  with fallback questions/scores.
- Bad: Browser JavaScript builds command strings for `codex`, `claude`, or
  embeds secrets.

### 6. Tests Required

- Python unit/API tests for summary, session start, scoring validation, P3
  fallback, and JSON error paths.
- HTTP smoke checks for `/`, static assets, and core APIs.
- Existing C++ CMake/CTest must remain green because the Web UI shares data and
  product contracts with the CLI.

### 7. Wrong vs Correct

#### Wrong

```js
fetch("/run-codex?prompt=" + encodeURIComponent(transcript));
```

#### Correct

```http
POST /api/score
Content-Type: application/json

{"part":"part2","transcript":"..."}
```

## Scenario: IELTS Web Training and Billing Ledger

### 1. Scope / Trigger

- Trigger: The IELTS web app now persists weak-question observations and a local wallet ledger for Codex usage settlement.
- Scope: `web/ielts_server.py`, `tests/test_ielts_web_server.py`, `reports/training/*`, `reports/billing/*`, and the related web UI settings/report views.

### 2. Signatures

```text
GET  /api/training/weak-items
GET  /api/training/replay-queue
GET  /api/billing/wallet
GET  /api/billing/wallet?user_id={user_id}
POST /api/billing/reserve
POST /api/billing/release
POST /api/billing/reconcile
POST /api/billing/settle-usage
```

### 3. Contracts

- Training observations are written after a scored attempt completes.
- Each observation stores stable `question_id`, `attempt_id`, `turn_id`, `part`, `question`, `transcript`, score dimensions, relevance, `weak_item_flag`, `weak_reason`, `observed_at`, and `next_due`.
- `GET /api/training/weak-items` returns aggregated weak items ordered by strongest weak signal and most recent observation, not by insertion order.
- `GET /api/training/replay-queue` prefers due weak items first and then keeps pending weak items in the queue.
- The billing wallet is stored in integer micro-RMB units.
- The initial local grant is exactly 5 RMB (`5_000_000` micro-RMB).
- Initial grant ledger idempotency is per user (`grant:initial:{user_id}`), not
  global, because local billing APIs can query or reserve balances for
  different `user_id` values.
- `POST /api/billing/reserve` accepts `call_id`, `reserved_u`, optional
  `snapshot_id`, optional `ttl_seconds`, and optional `user_id`. It deducts
  `reserved_u` from available balance, increments `reserved_u`, writes a
  `reserve` ledger entry, and is idempotent by `call_id`.
- `POST /api/billing/release` accepts `call_id` and optional `user_id`. Once a
  reservation exists, the reservation owner is authoritative; release must
  restore the owner wallet balance and must not credit an arbitrary requester.
- `POST /api/billing/reconcile` accepts `call_id`, optional `usage`, optional
  `snapshot_id`, and optional `user_id`. It delegates to settlement. If the
  `call_id` has a reserved wallet row, settlement must debit/release against
  the reservation owner, not the requester.
- `POST /api/billing/settle-usage` must treat `call_id` as the idempotency key for settlement.
- Cached input tokens, uncached input tokens, and output tokens are charged separately from the active price snapshot.
- `reasoning_output_tokens` are captured for auditability but do not contribute to the current charge.
- Missing authoritative usage returns a pending reconciliation response and must not guess a charge.
- If actual usage is lower than a reservation, reconciliation settles the
  actual charge and releases the unused reservation back to available balance.
- If actual usage is higher than a reservation, reconciliation consumes the
  reservation and deducts only the extra charge from available balance.
- Releasing a reservation after it has already been settled must be a no-op and
  must not double-credit the wallet.

### 4. Validation & Error Matrix

- Scored attempt without weak candidates -> no weak-item rows are emitted.
- Weak-item query with no matches -> empty list, not an error.
- Missing `call_id` -> `400` JSON error.
- Missing or non-positive `reserved_u` on reserve -> `400` JSON error.
- Reserve amount greater than available balance -> `400` JSON error.
- Release for an unknown reservation -> `400` JSON error.
- Missing `usage` -> `pending_reconciliation`, zero charge.
- Repeated `call_id` settlement -> `already_settled`, no duplicate charge.
- Repeated `call_id` reserve -> return the existing reservation, no duplicate
  deduction.
- Repeated release of a released reservation -> return the existing released
  reservation, no duplicate credit.
- Snapshot lookup failure -> explicit error, not a fallback charge guess.

### 5. Good/Base/Bad Cases

- Good: A scored attempt records weak-question rows, and the UI can surface a replay queue.
- Base: The wallet starts with a known local grant and the recent ledger can be inspected in the UI.
- Good: A call reserves 0.30 RMB, later releases it, and the wallet balance and
  reserved balance return to their starting values.
- Good: A call reserves 2.00 RMB, actual usage costs 0.12 RMB, and reconciliation
  releases the remaining 1.88 RMB while preventing a later release from
  crediting again.
- Bad: Treating `reasoning_output_tokens` as billable output again; that double-counts the request.
- Bad: Reconciling an existing reservation with a different request `user_id`
  and charging or releasing the requester instead of the reservation owner.

### 6. Tests Required

- Scored-attempt test must assert weak observations are persisted and listed by `/api/training/weak-items`.
- Replay queue test must assert weak/due items are surfaced first.
- Wallet test must assert the initial balance is exactly 5 RMB in micro-RMB.
- Settlement test must assert cached and uncached input tokens are charged differently.
- Settlement test must assert repeated `call_id` settlement is idempotent.
- Missing-usage test must assert no blind deduction occurs.
- Reserve/release test must assert reservation idempotency and balance restoration.
- Reservation settlement test must assert unused reservation release and no
  second release after settlement.
- Reservation owner test must assert reconciliation uses the reservation owner
  when the request `user_id` differs.

### 7. Wrong vs Correct

#### Wrong

```python
if usage:
    charge = estimate_charge_from_prompt(payload)
```

#### Correct

```python
if not usage:
    return {"status": "pending_reconciliation", "charged_u": 0}
```

#### Wrong

```python
conn.execute("UPDATE users SET balance_u = balance_u + ? WHERE user_id = ?", (released_u, payload_user_id))
```

#### Correct

```python
owner_user_id = reservation["user_id"]
conn.execute("UPDATE users SET balance_u = balance_u + ? WHERE user_id = ?", (released_u, owner_user_id))
```
