# CHANGES

## Summary

Refactored `backend_django/apps/ai/provider_adapters.py` into explicit provider-pattern building blocks while preserving the existing public import path and AI task behavior.

## Files Changed

* `backend_django/apps/ai/provider_adapters.py`

## Added Structures

* `AIProvider`
  * Strategy interface for durable AI provider adapters.
* `AiTaskTemplate`
  * Template Method base class for provider-backed task execution.
  * Centralizes request payload extraction, provider execution, parsing, success result construction, and terminal failure mapping.
* `CodexCliClient`
  * Adapter around the local Codex CLI JSON event stream.
  * `run_codex(...)` remains available from `apps.ai.provider_adapters` and delegates to this client.
* `ProviderChain`
  * Chain-of-responsibility wrapper around selected providers.
  * Current behavior remains preserving: Codex writing failures still terminal-fail as before, matching existing tests.
* `ProviderExecutionError`
  * Small typed exception for provider failures that need a specific `error_code`.

## Compatibility Preserved

The original module path still exports the public names used by tests, worker code, and product code:

* `run_codex`
* `CodexWritingScoreAdapter`
* `CodexSpeakingReportAdapter`
* `FallbackWritingScoreAdapter`
* `MockSuccessWritingScoreAdapter`
* `ProviderRunResult`
* `AppliedProviderRunResult`
* `apply_provider_run_result`
* `run_claimed_ai_task`
* `select_provider_adapter`
* `DEFAULT_FALLBACK_REASON`
* `SUMMARY_STATUS_SKIPPED`

Tests that patch `apps.ai.provider_adapters.run_codex` still work because `CodexWritingScoreAdapter` calls the module-level `run_codex(...)`.

## Before / After

Before:

* Provider adapters each owned their own `run()` orchestration.
* Codex CLI execution lived as a large function with a hidden fallback from JSON mode to non-JSON mode.
* Provider selection returned a single concrete adapter directly.

After:

* Provider adapters share the `AiTaskTemplate.run()` execution skeleton where applicable.
* Codex CLI execution is isolated in `CodexCliClient`.
* `run_codex(...)` no longer silently performs a second non-JSON Codex run after JSON execution errors.
* Provider selection returns a `ProviderChain`, keeping a visible chain boundary without changing task terminal behavior.

## Behavior Notes

* Writing Codex failures still produce `FAILED` tasks with `error_code=codex_writing_score_failed`.
* Speaking report missing `attempt_id` still uses `error_code=missing_attempt_id`.
* Fallback output remains explicitly marked as fallback and cannot become `SUCCESS`.
* No product prompts, scoring payloads, billing transitions, or frontend behavior were changed.

## Validation

```text
cd backend_django
../.venv-django/bin/python manage.py test apps.ai -v 1
52 tests passed

../.venv-django/bin/python manage.py test apps.ai apps.writing -v 1
94 tests passed

../.venv-django/bin/python manage.py test -v 1
231 tests passed

../.venv-django/bin/python manage.py check
System check identified no issues

../.venv-django/bin/python manage.py makemigrations --check --dry-run
No changes detected

node --check web/static/app.js
passed
```
