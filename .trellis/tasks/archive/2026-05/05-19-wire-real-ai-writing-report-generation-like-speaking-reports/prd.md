# Wire Real AI Writing Report Generation Like Speaking Reports

## Goal

Make Writing reports use a real Codex-generated analysis pipeline, like Speaking reports. The current UI can render structured writing reports, but the worker still falls back to local scoring, so users see fake/default text such as "暂无 AI 改写" and generic paragraph advice. This task wires the writing score worker to Codex and requires the Codex result to produce the report fields shown in the UI.

## What I Already Know

- Speaking already has a working `run_codex()` wrapper with JSON event parsing, stdin `-`, token validation, and real-content validation.
- Writing score tasks currently route through `FallbackWritingScoreAdapter` for normal `codex` requests, so reports are fallback by design.
- The previous task correctly made `backend="ai"` require AI-supplied structured analysis, but no real writing provider exists yet.
- The screenshot proves the user is still seeing fallback reports, not AI reports.

## Requirements

- Add a real Codex writing score adapter for `task_type="writing_score"` when provider is `codex` and Codex is enabled.
- Reuse the speaking Codex execution behavior or a shared equivalent: stdin `-`, JSON event parsing, input-token validation, empty-output validation, and real-content validation.
- Prompt Codex to return JSON only with:
  - IELTS scores and criterion bands
  - `feedback_markdown`
  - `grammar_corrections`
  - `overall_review`
  - `practice_focus`
  - `model_answer`
  - `paragraph_reviews`
  - `structure_advice_only`
  - `structure_advice`
- Paragraph analysis must be AI-driven. AI decides whether the essay can be mapped paragraph-by-paragraph or should become structure-advice-only.
- Report text should feel like the Speaking report: specific, based on the submitted essay, not generic placeholders.
- If Codex fails or returns invalid JSON, fall back explicitly; do not present fallback as AI report.
- Keep local fallback for unavailable Codex, tests, and resilience.

## Acceptance Criteria

- [x] Normal `provider=codex` writing score worker attempts a real Codex call instead of immediately using fallback.
- [x] Valid Codex JSON persists `backend="ai"` with non-empty `overall_review`, `practice_focus`, and paragraph reviews or structure advice.
- [x] Missing/invalid Codex structured fields trigger fallback, not fake AI report generation.
- [x] Fallback report remains clearly marked as fallback.
- [x] Tests cover Codex adapter success with structured paragraph reviews.
- [x] Tests cover invalid Codex output falling back.
- [x] Existing writing/AI tests pass.
- [x] Full Django tests pass.
- [x] JS syntax check passes.

## Out of Scope

- UI redesign beyond preventing fake AI presentation.
- New external provider other than local Codex CLI.
- Production deployment config.

## Technical Notes

- Main files: `backend_django/apps/ai/provider_config.py`, `backend_django/apps/ai/provider_adapters.py`, `backend_django/apps/ai/tests.py`, maybe `backend_django/apps/writing/services.py`.
- Speaking reference: `backend_django/apps/speaking/services.py::run_codex`, `turn_feedback_with_codex`, `score_with_codex`.
