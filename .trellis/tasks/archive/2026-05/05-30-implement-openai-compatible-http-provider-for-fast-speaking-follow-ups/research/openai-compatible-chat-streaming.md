# Research: OpenAI-compatible Chat Completions streaming

- Query: Research OpenAI-compatible Chat Completions streaming usage for fast speaking follow-ups; include request shape, SSE parsing rules, timeout/error handling implications, and API-key security notes.
- Scope: mixed
- Date: 2026-05-30

## Findings

### Files Found

- `backend_django/apps/speaking/services.py` - current follow-up hot path; P3 quick follow-ups spawn Codex CLI and parse a single question.
- `backend_django/apps/ai/provider_adapters.py` - existing provider strategy/result/fallback scaffolding for durable AI tasks.
- `backend_django/apps/ai/provider_config.py` - provider routing config already knows `openai` as a future provider, but routes only Codex/fallback today.
- `backend_django/config/settings.py` - reads provider enable flags and secret env-var names from environment-backed settings.
- `docs/SPEC-http-api-provider-followup-latency.md` - goal spec requiring `AI_HTTP_BASE_URL`, `AI_HTTP_API_KEY`, `AI_HTTP_MODEL`, streaming-first HTTP, and Codex fallback.
- `.trellis/spec/backend/error-handling.md` - backend provider failures should map to explicit retry/fallback/terminal states without leaking provider internals.
- `.trellis/spec/backend/logging-guidelines.md` - AI task logs may include safe routing facts only; never log provider secret values or raw env secret strings.

### Code Patterns

- Current P3 dynamic follow-up flow computes a local fallback first, then tries `quick_follow_up_runner`, and returns `backend/status/error` metadata on failure (`backend_django/apps/speaking/services.py:889`).
- `quick_follow_up_runner` currently builds a one-line examiner prompt, shells out to `codex exec`, enforces a 12s timeout, and extracts one valid question (`backend_django/apps/speaking/services.py:817`, `backend_django/apps/speaking/services.py:854`, `backend_django/apps/speaking/services.py:881`).
- P3 output validation rejects non-question text, multiple questions, overlong text, JSON/Markdown artifacts, and echoed prompt labels (`backend_django/apps/speaking/services.py:756`, `backend_django/apps/speaking/services.py:792`).
- P1 identity follow-up expects JSON with a top-level `follow_up`, caps length at 160 chars, requires a question mark, then falls back on any exception (`backend_django/apps/speaking/services.py:1572`).
- `ProviderRunResult` already models success, fallback, retryable failure, terminal failure, skipped, usage, error codes, and safe metadata (`backend_django/apps/ai/provider_adapters.py:43`).
- `ProviderChain` currently returns the first provider result whose outcome is not `SKIPPED`; an HTTP-to-Codex fallback chain would need HTTP failures represented carefully if fallback should continue rather than terminal-fail immediately (`backend_django/apps/ai/provider_adapters.py:624`).
- Provider config includes `openai` in known providers and enable flags, but currently unresolved real providers fall back with "adapter is not wired" (`backend_django/apps/ai/provider_config.py:19`, `backend_django/apps/ai/provider_config.py:26`, `backend_django/apps/ai/provider_config.py:216`).
- Settings expose `AI_PROVIDER_ENABLE_OPENAI` and placeholder secret env names only; current task-specific env names `AI_HTTP_BASE_URL`, `AI_HTTP_API_KEY`, and `AI_HTTP_MODEL` are not present yet (`backend_django/config/settings.py:152`, `backend_django/config/settings.py:158`).

### Request Shape

- Use `POST {AI_HTTP_BASE_URL.rstrip("/")}/chat/completions` so `AI_HTTP_BASE_URL` can be `https://api.openai.com/v1` or a compatible provider base URL.
- Required headers: `Content-Type: application/json`; `Authorization: Bearer <AI_HTTP_API_KEY>`.
- Minimal streaming body for this task:

```json
{
  "model": "<AI_HTTP_MODEL>",
  "messages": [
    {"role": "system", "content": "You are an IELTS Speaking examiner."},
    {"role": "user", "content": "<one-follow-up prompt>"}
  ],
  "stream": true,
  "stream_options": {"include_usage": true},
  "temperature": 0.4,
  "max_tokens": 80
}
```

- For OpenAI's current Chat Completions API, streamed chunks carry generated text in `choices[0].delta.content`. Some providers/models may require `max_completion_tokens` instead of `max_tokens`; for broad compatibility, keep this configurable or use the provider's documented parameter if failures identify an unsupported field.
- `stream_options.include_usage=true` asks for a final usage chunk before `[DONE]`; all earlier chunks can have `usage: null`, and interrupted streams may never deliver final usage.

### SSE Parsing Rules

- Treat the response as UTF-8 `text/event-stream`; parse incrementally by SSE event, not by arbitrary socket chunks.
- Normalize CRLF/CR to LF. Accumulate `data:` lines until a blank line terminates an event. Ignore comment lines starting with `:` and unknown fields such as `event:`.
- For each event, concatenate multiple `data:` lines with `\n` per SSE semantics, then:
  - If payload is `[DONE]`, stop normally.
  - Else parse payload as JSON.
  - Append each non-empty `choice.delta.content`.
  - Track `choice.finish_reason`; `stop` is normal, `length` means truncation, `content_filter` or unexpected finish reasons should be provider failure for this follow-up use case.
  - If `choices` is empty and `usage` is a dict, save usage and continue to `[DONE]`.
- Compatible providers sometimes send error JSON inside a streamed `data:` event or return non-SSE JSON on non-2xx responses; handle both as provider errors and avoid passing raw provider text to users.
- After stream completion, run the existing one-question validators (`_extract_single_follow_up_question` for P3 and JSON/length/question validation for P1). A syntactically valid stream with empty/invalid content should trigger Codex fallback, not local success.

### Timeout And Error Handling Implications

- Separate connect timeout, first-byte/read timeout, and total request deadline. For the real-time follow-up path, HTTP should fail quickly enough to leave room for Codex/local fallback; a practical starting point is connect around 1-2s and total HTTP deadline below the current Codex follow-up timeout (`P3_QUICK_FOLLOW_UP_CODEX_TIMEOUT = 12`, `P1_FOLLOW_UP_CODEX_TIMEOUT = 15`).
- Streaming read timeout should mean "no bytes/chunks for N seconds", not "entire stream must finish in N seconds"; still enforce an overall deadline because user-visible follow-ups need bounded latency.
- Classify likely retry/fallback behavior:
  - Missing `AI_HTTP_BASE_URL`, `AI_HTTP_API_KEY`, or `AI_HTTP_MODEL`: configuration failure; skip HTTP and fall back without retry.
  - HTTP 400/422: request-shape/model-parameter bug; fall back and surface sanitized metadata for diagnosis.
  - HTTP 401/403: credential/permission failure; do not retry in the hot path.
  - HTTP 408/429/5xx or network timeout/reset: transient; at most one very quick retry if it still fits the latency budget, otherwise fall back to Codex.
  - Stream interrupted before `[DONE]`: accept only if already collected a valid complete question; otherwise fall back. Usage may be unavailable.
- Always close the streaming response on timeout, validation failure, or early exit to avoid leaking sockets.
- Preserve explicit metadata: HTTP success should mark backend like `http_openai_compatible`; HTTP failure followed by Codex success should not pretend HTTP succeeded; final local fallback should include sanitized failure reason/status.

### Security Notes For API Keys

- Read API keys only from environment (`AI_HTTP_API_KEY` for this task); do not commit keys, write them into settings defaults, persist them in task metadata, return them in API responses, or log them.
- Keep OpenAI-compatible calls server-side only. Never expose provider keys to browser JavaScript, mobile clients, frontend templates, or client-visible config endpoints.
- Log safe routing facts only: provider name, model name if not secret, base URL host if needed, timeout category, HTTP status, and sanitized error code. Do not log request headers, full request body when it could contain user PII, or provider error text that may echo key fragments.
- Treat base URL as trusted server configuration, not user input. If future UI allows editing it, validate scheme/host and block local/private network targets to avoid SSRF.
- Use per-environment/per-provider keys with limited permissions where available; rotate any key suspected to have been committed or logged.

### External References

- Context7 `/websites/developers_openai_api`, OpenAI Chat Completions curl example: `POST https://api.openai.com/v1/chat/completions` with `Content-Type: application/json`, `Authorization: Bearer $OPENAI_API_KEY`, `model`, and `messages`. Source: https://developers.openai.com/api/docs/guides/responses-vs-chat-completions
- Context7 `/websites/developers_openai_api`, OpenAI streaming examples: `stream: true`; clients iterate chunks and read `chunk.choices[0].delta.content`. Source: https://developers.openai.com/api/docs/guides/predicted-outputs
- Context7 `/websites/developers_openai_api`, ChatCompletionStreamOptions: `stream_options.include_usage` adds a usage chunk before `data: [DONE]`; usage may be missing if the stream is interrupted. Source: https://developers.openai.com/api/docs/api-reference/chat/object
- Context7 `/websites/developers_openai_api`, ChatCompletionChunk delta: streamed model text appears in `choices[].delta.content`. Source: https://developers.openai.com/api/docs/api-reference/chat/create
- OpenAI API error guide: 401 indicates invalid/incorrect auth, 429 indicates rate/usage limit, 500/503 indicate server overload/errors, and timeout/connection failures should be handled programmatically. Source: https://platform.openai.com/docs/guides/error-codes
- OpenAI API key safety guide: do not deploy keys client-side, do not commit keys, and use environment variables. Source: https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety

### Related Specs

- `docs/SPEC-http-api-provider-followup-latency.md` - task goal, env-var names, HTTP-first then Codex/fallback chain, and no-key red lines.
- `.trellis/spec/backend/index.md` - AI feedback should be provider-generated when available, and fallback/failed states must remain transparent.
- `.trellis/spec/backend/error-handling.md` - do not leak provider internals to clients; expected provider failures should map to deterministic task/fallback behavior.
- `.trellis/spec/backend/logging-guidelines.md` - never log provider secrets or copied environment secret strings.

## Caveats / Not Found

- I did not find an implemented `HttpApiProvider`; existing `openai` routing is configuration scaffolding only.
- OpenAI-compatible providers vary: some omit `stream_options`, use different token-limit field names, send malformed SSE, or return OpenAI-shaped non-streaming JSON despite `stream=true`. The client should degrade gracefully to non-streaming only if explicitly supported by the task design; otherwise fall back to Codex.
- The current `ProviderChain` returns on any non-`SKIPPED` result, so an HTTP adapter that returns `TERMINAL_FAILURE` would prevent Codex fallback. Implementation should either use a follow-up-specific chain or represent HTTP "try next provider" failures distinctly.
- `config/default_config.json` contains an apparent committed API-key-looking value. I did not modify it because this research task permits writing only under the task `research/` directory; implementation/security cleanup should avoid copying this pattern and should rotate any real exposed key.
