# Runtime checks (unattended)

- Original user server: localhost 8767, PID 31665; preserved. Original desktop process PID 34606 preserved because graceful GUI exit is unavailable while locked.
- New fresh SQLite QA database under chat work/, synthetic account only, localhost 8768. No public tunnel/worker/device changes.
- First HTTP integration pass: 20 checks passed against actual localhost server, 30 curated questions. Authentication/CSRF, creation, current answer/save/duplicate/conflict, AI follow-up unavailability preserving progress, skip, detail reload, finish/report/history, duplicate finish, AI coaching failure and custom AI failure, manual custom session/abort.
- Later implementation adds durable coaching failure marker; final pass must assert transcript/counts preserved and marker retryable rather than entire report byte-for-byte unchanged.
- CUA inventory initially timed out; specific getApp revealed Mac locked, automatic unlock unavailable. No unlock prompt issued because user explicitly requested no questions while away. No alternative UI automation used. Actual visual/motion acceptance pending unlock.
- No real resume, paid AI request or microphone capture made. Software/API tests and compile checks continue independently of GUI availability.
