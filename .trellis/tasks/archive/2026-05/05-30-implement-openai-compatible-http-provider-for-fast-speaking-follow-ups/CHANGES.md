# Changes

## Implementation

- Added an OpenAI-compatible HTTP provider in `backend_django/apps/ai/http_provider.py`.
- The provider reads `AI_HTTP_BASE_URL`, `AI_HTTP_API_KEY`, `AI_HTTP_MODEL`, and optional `AI_HTTP_TIMEOUT_SECONDS` from environment/settings only.
- P3 follow-up generation now tries HTTP first, then Codex CLI, then explicit local fallback metadata.
- P1 identity follow-up generation now tries HTTP first, then Codex CLI, then explicit local fallback metadata. HTTP output may be either `{"follow_up": "..."}` JSON or one plain question, so compatible endpoints are not forced through an unnecessary JSON-only retry path.
- Added `scripts/benchmark_followup_providers.py` to compare provider availability and latency without printing secrets.

## Validation

- Added focused tests:
  - `backend_django/apps/ai/test_http_provider.py`
  - `backend_django/apps/speaking/test_http_followups.py`
- The tests cover missing HTTP config, streaming chunk parsing, secret redaction, HTTP success routing, plain-text P1 HTTP output, HTTP-to-Codex fallback, and explicit local fallback metadata.
- Check pass:
  - `python3 backend_django/manage.py check`
  - `python3 backend_django/manage.py test apps.ai.test_http_provider apps.speaking.test_http_followups`
  - `python3 backend_django/manage.py test apps.ai`
  - `python3 backend_django/manage.py test`
  - `python3 backend_django/manage.py makemigrations --check --dry-run`
  - `python3 scripts/benchmark_followup_providers.py --rounds 1 --skip-codex`

## Limitations

- Real latency numbers require valid `AI_HTTP_*` environment variables and an available Codex CLI for comparison.
- The frontend is unchanged; this task only changes backend provider routing for follow-up generation.
- Provider failures are sanitized and surfaced as routing metadata, not as successful AI output.
