# Desktop mock interview MVP and native voice baseline

## Authorization and outcome
The user wants a working desktop mock interview UI and functionality, and a serious C++ low-latency voice foundation. They will return in about two hours and explicitly requested recommended defaults without questions. Local ui-polish work and commits only; no push, VPS purchase, worker auto-start or actual microphone capture while absent. Existing dirty backend_django/db.sqlite3 must remain excluded and untouched by migrations; use an isolated development database.

## Product scope
- Desktop-only mock interview mode, authenticated by real Qt QWebChannel capability discovery; keep IELTS web and desktop behavior working.
- Accessible top-left mode switcher; inspect detail.design motion reference before implementation, record the source and observations. Honor reduced motion. Retain global account/settings and three-way appearance.
- Interview home, general question bank (C++, low latency, systems, projects, behavioral), custom questions from resume text/PDF plus job description, answering, optional follow-up, completion, saved history and transcript report.
- Typed answers are fully functional now. UI states honestly explain native voice is being connected; never represent browser ASR or simulated audio as native live speech. No inactive controls masquerading as working functionality.
- AI customization, follow-up and coaching use configured existing server AI provider/accounting patterns. Failures are visible and retryable. Curated question practice and transcript summary work without AI credentials. No fabricated AI scores or fallback personalized questions.
- Separate apps.interview in the same Django deployment; share account/provider infrastructure. No broad IELTS service refactor.

## Stable frontend/backend contract (coordinated by root)
All /api/interview/ endpoints require the existing authenticated Django session, CSRF on writes, owner isolation, JSON responses/errors consistent with repository.
GET questions/ -> {questions:[{id,category,prompt,difficulty,source}],categories:[{id,label}]}; optional category query.
POST custom-questions/ multipart resume_file (PDF optional), resume_text, job_description, count (1..10), ai_source -> {questions:[{prompt,category,difficulty,source}], resume_excerpt?}. Validate file/length and redact provider errors.
POST sessions/ JSON {mode:'general'|'custom',category?,count?,question_ids?,questions?,title?} -> {session,turns,current_turn}; general selects validated bank IDs or category, custom validates generated/edited prompts. Session: {id,mode,title,status:'active'|'completed'|'aborted',current_turn_id,created_at,updated_at,report}. Turn: {id,order,kind:'main'|'follow_up',question_id?,prompt,answer,status:'pending'|'completed'|'skipped',source}.
GET sessions/ -> {sessions:[session]}; GET sessions/<id>/ -> {session,turns,current_turn}.
POST sessions/<id>/turns/<turn_id>/answer/ JSON {answer} saves current answer, advances atomically; duplicate same payload idempotent, conflicting stale submission rejected.
POST sessions/<id>/turns/<turn_id>/skip/ advances; no answer required.
POST sessions/<id>/turns/<turn_id>/follow-up/ JSON {ai_source?} for completed turn -> inserts a pending AI follow-up after it; supported once per parent, no interleaving unbounded calls. Failure must not alter session.
POST sessions/<id>/finish/ closes remaining pending turns as skipped, durable transcript report; duplicate finish idempotent. POST sessions/<id>/abort/ aborts.
POST sessions/<id>/report/ JSON {ai_source?} -> {session,turns,current_turn}; completed only, real AI coaching stored in report.ai_feedback with explicit text-derived limits. Deterministic report includes completed/skipped counts, transcript; never implies audio/pronunciation assessment.
Use trailing slashes in client. Error: {error:<safe message>,code?:<stable code>} with proper 400/401/403/404/409/502.
Backend implementer may refine minor serialization consistently but MUST notify frontend agent/root before changing contract. Asset allowlist adds native-bridge.js and interview.js; CSS stays styles.css.

## Native foundation scope
Independent native_voice/ CMake C++17 core (no mandatory Qt), bounded preallocated single-producer/single-consumer capture/playback buffers, owned cancellable worker, explicit epochs, callback-safe capture/render, immediate interrupt silence, deterministic software harness and tests. Qt >=6.11 callback adapter; optional PortAudio callback adapter if available or practical dependency install, compare honestly under identical formats. Actual hardware mode explicit opt-in, simulated mode default. No microphone/audio device start during this unattended work.
Measure real observed software latency distributions, counts, overruns/underruns, stale discards, memory bounds. No industrial/physical/device performance claims from synthetic results. Preserve sample rate, channels, partial block handling and shutdown guarantees. Existing old engine not linked into desktop. Add concise README and cross-layer lifecycle spec.

## Acceptance
- End-to-end create, answer, follow-up failure/success fixtures, skip, finish, reload history and transcript; authentication/ownership/CSRF/validation and idempotency tests.
- Valid PDF/text input and provider failure behavior tested without paid/live generation calls.
- Desktop capability bridge tested and browser mode remains IELTS-only; switcher keyboard/Escape/outside/reduced-motion, no new browser speech recognition.
- UI visually inspected in actual desktop or safe dedicated capability fixture, saved screenshots; truthful report limitations.
- Native C++ tests and simulated benchmark run; callback adapters compile against installed API. Meaningful concurrency/lifecycle and sanitizer coverage where platform permits.
- Existing frontend and desktop meaningful regression checks. No real recording, secrets in client, live billing calls, deployment or changes to preexisting database.
