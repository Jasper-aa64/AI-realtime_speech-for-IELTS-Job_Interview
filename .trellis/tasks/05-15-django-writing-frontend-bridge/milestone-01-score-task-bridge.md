# Milestone 01: Writing score-task bridge

## Goal

Make the existing vanilla Web writing UI use Django's durable writing score task flow for logged-in users, while preserving the old JSON writing fallback when Django writing proxy is not active.

## Scope

Changed the old Web frontend, old-server Django proxy boundary, one old Web server test, the frontend code-spec, and this Trellis task's planning documents.

## Changed Files

- `web/static/app.js`
- `web/static/styles.css`
- `web/ielts_server.py`
- `tests/test_ielts_web_server.py`
- `.trellis/spec/frontend/quality-guidelines.md`
- `.trellis/tasks/05-15-django-writing-frontend-bridge/prd.md`
- `.trellis/tasks/05-15-django-writing-frontend-bridge/implement.jsonl`
- `.trellis/tasks/05-15-django-writing-frontend-bridge/check.jsonl`

## Design Decisions

- The frontend now saves the writing entry first, then tries `POST /api/writing/entries/{entry_id}/score-task`.
- The frontend polls `GET /api/writing/entries/{entry_id}` as the recovery surface instead of trusting in-memory scoring state.
- Legacy synchronous `/score` fallback is only used for the old-server `404 Unknown API endpoint` case, so real Django billing/auth/validation errors are not silently hidden.
- The old web server proxies `/api/ai/tasks/*` when a Django `sessionid` cookie is present, matching the writing proxy path and leaving room for pending cancellation from the old origin.
- Active task states disable editing controls and show the inline wait block; worker completion switches to the writing report view when the result appears.

## Verification

- `node --check web/static/app.js` passed.
- `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py` passed.
- `python3 -m unittest discover -s tests -p 'test_*.py'` passed: 56 tests.
- `.venv-django/bin/python backend_django/manage.py check` passed.
- `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run` passed with no changes detected.
- `.venv-django/bin/python backend_django/manage.py test` passed: 75 tests.
- Browser smoke passed on `http://127.0.0.1:8765/`: registered/logged in through proxied Django account API, opened 每日写作, submitted AI scoring, observed `AI 评分已排队`, ran `run_ai_tasks --limit 5`, and verified the UI switched to 写作报告 with Band, fallback feedback markdown, profile, prompt, and answer.

## Known Issues

- The worker is still manual/local for this milestone; there is no always-on background worker supervisor yet.
- The frontend does not yet expose a visible cancel button for pending writing score tasks, although the old-origin proxy path is now available.
- Browser smoke used the deterministic fallback provider path; real provider SDK integration remains out of scope.
- The trellis-check subagent was spawned but hit API 429 before returning; main-session checks and browser smoke completed successfully.

## Rollback

- Revert `web/static/app.js`, `web/static/styles.css`, `web/ielts_server.py`, and `tests/test_ielts_web_server.py` to return the writing UI to synchronous `/score`.
- Keep Django data untouched; score task rows created during local smoke are development data only.
- If proxy behavior causes issues, set `IELTS_DJANGO_PROXY_WRITE_FIRST=0` to keep old writing endpoints local while accounts remain proxied.

## Next Stage

- Add a supervised local/Django worker loop or management wrapper so pending AI tasks progress without manually running `run_ai_tasks`.
- Add a pending-only cancel control in the writing UI.
- Extend the same durable task pattern to slow speaking report scoring once the Django speaking API is ready.
