# Interview Workflow

## Scope

`apps.interview` is a separate domain inside the existing Django service. It
shares accounts, AI provider configuration and billing-aware tasks. IELTS band,
Band 7 coaching and speaking training models must not become interview scores.

## HTTP and ownership boundary

- `/api/interview/*/` uses trailing slashes, authenticated Django sessions and
  normal CSRF checks on writes. Return JSON 401/403/404/409/502 errors.
- Scope every session lookup by owner. Scope turns to that session and owner.
  Missing and wrong-owner IDs both return 404; desktop capability is UI gating,
  not server authorization.
- Validate explicit input types/bounds: 1–10 main questions, unique curated
  IDs, 1,500-character questions, 6,000-character answers, 24,000-character
  resumes and 12,000-character job descriptions. Reject malformed JSON.
- List at most 100 sessions and return report summaries; session detail is
  the only endpoint that returns full transcript/feedback text.

## Atomic state transitions

- Service layer owns `transaction.atomic()` and `select_for_update()` on
  sessions. Views only parse input, dispatch and translate errors.
- Answer/skip requires the current pending turn. Same canonical answer/skip
  is idempotent; conflicting stale writes return 409.
- Finish skips remaining pending turns, persists one deterministic report and
  changes status to completed. Repeat finish must preserve the saved report.
- Follow-up is permitted once per answered main and before later progress.
  Its OneToOne parent and unique session/order prevent duplicate children.
  Shift pending orders descending inside the transaction before insertion.
- Provider work must run outside session transactions. A 180-second lease
  prevents answer/finish/interleaving generation; a fresh random lease token
  rejects late output after recovery. Owned cleanup cannot clear another lease.
- Abort and completion are durable. Do not reopen closed sessions as an
  implicit retry or use client state as the authoritative transcript.

## AI and reporting boundary

- Use shared configured HTTP/account sources and existing CLI adapters;
  explicit source failures remain visible. No personalized local substitute
  may pretend to be successful AI output.
- Synchronous request creates and claims a billing-aware `AITask` in one
  transaction. Provider work needs no background worker startup. Validated
  success settles usage through `apps.ai.orchestration`; error terminal-fails
  through the same boundary with safe messages. Never expose/log provider
  exception details, secrets, resumes or answers.
- Curated practice and transcript reports must work without AI credentials.
  Report explicitly states typed/text-only limits, completed/skipped counts
  and ordered transcript. No pronunciation/audio assessment or invented score.
- AI coaching adds ready feedback with real provider/model/task identity and
  observed elapsed timing. Safe failed feedback survives reload and permits
  retry; it must not replace the saved transcript. Ready feedback is idempotent.
- Client-supplied custom prompts are `user_custom`; only server generation
  may attest `ai_generated` provenance. Never trust a posted source flag.

## PDF process boundary

Use `pdftotext` via structured arguments, no shell. Cap input at 2 MB, pages
at 20, wall time at 10 seconds, output during execution at 96 KB and final text
at 24,000 characters. Discard stderr, kill oversized/timed-out children and
wait for them. Missing tool/scanned/encrypted/invalid input returns a safe
error with resume-text fallback. Do not save uploaded resume files.

## Required validation

- Auth/CSRF/owner isolation on every mutation and detail/history read.
- Create→answer→skip→finish→reload/history, duplicate and conflicting stale
  writes, aborted sessions, one follow-up, busy interleaving and late generation.
- Mocked configured provider success/usage settlement, redacted terminal
  failures, invalid output, failed coaching reload/retry and idempotent success.
- Bounded PDF output/timeout/missing reader plus a real small text-PDF fixture
  when the local reader exists; no paid API calls or actual microphone capture.
- Use a test or explicitly isolated development DB. Never migrate the owner's
  existing tracked `backend_django/db.sqlite3` for unattended MVP work.
