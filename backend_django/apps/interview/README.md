# Interview app

Desktop UI exposes this app after real Qt capability discovery. The server uses
the existing authenticated Django session, normal CSRF protection, and owner
scoping; a desktop capability is not an authorization credential.

All endpoints are under `/api/interview/`, with trailing slashes. The current
MVP supports typed answers, curated practice and deterministic transcript
reports without AI credentials. It does not record audio or evaluate
pronunciation, and produces no invented score or personalized fallback output.

- `GET questions/`: curated bank and categories, optional category filter.
- `POST custom-questions/`: resume text or PDF plus job description, 1–10
  AI-generated questions. Uses configured account provider synchronously.
- `GET/POST sessions/`: newest 100 session summaries / create general or custom
  session. List reports omit transcript/AI feedback text; fetch detail to view.
- `GET sessions/<id>/`: full session, ordered turns and current turn.
- `POST sessions/<id>/turns/<turn>/answer/` or `skip/`: atomic current-turn
  transition; identical submission is idempotent, conflicting stale write is 409.
- `POST .../follow-up/`: one follow-up for a completed main, before any later
  answered/skipped turn. In-flight generation blocks concurrent progress.
- `POST sessions/<id>/finish/`: skip pending turns and persist the text-only
  transcript report. Repeating finish returns the same stored report.
- `POST .../abort/`: durable aborted session.
- `POST .../report/`: completed-session AI coaching; `report.ai_feedback` has
  explicit `ready` or safe `failed` status and text-only limitations. Failure
  preserves the transcript and is retryable; ready coaching is idempotent.

Custom session creation always labels submitted/edited prompts `user_custom`,
even if the client claims they were AI generated. The generation endpoint
records real AI provenance, but arbitrary client fields cannot attest it. AI
follow-ups created server-side are `ai_generated` and retain the task identity.

AI calls reuse existing account source configuration, shared HTTP/CLI adapters
and billing-aware `AITask` lifecycle. Create+claim is atomic before provider
work, so no worker startup is required and no pending job is left for the
general worker. Provider failures/malformed outputs terminate safely without
logging prompts, resumes, answers or provider secrets. Usage is settled through
the existing orchestration helper, with observed request/provider elapsed time;
unavailable internal first-token timings are not fabricated.

PDF extraction requires the `pdftotext` executable (Poppler). If unavailable,
the API explicitly asks for pasted resume text. The PDF input is limited to
2 MB, the first 20 pages, 10 seconds and at most 96 KB extracted UTF-8 bytes /
24,000 text characters. Stderr is discarded and stdout is capped during
extraction, killing oversized/slow processes. Scanned/encrypted/invalid PDFs
return a safe error. No resume files are saved on disk.

For local development use an isolated database via `DJANGO_DB_NAME`, then
migrate that database. Do not migrate the owner's tracked `db.sqlite3` as part
of this MVP. Run `manage.py test apps.interview`; all provider calls in tests
are mocked. One PDF fixture uses real local extraction only, if available.
