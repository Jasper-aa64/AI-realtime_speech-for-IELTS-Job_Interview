# Make Writing Report Paragraph Analysis AI Driven

## Goal

Fix the writing report analysis layer so paragraph grouping and per-paragraph advice come from the AI scoring result, not from local hard-coded templates. Local code may still validate that the user has at least visible paragraph breaks before scoring, but it must not pretend to know the logical paragraph roles or generate model paragraphs by fixed rules.

## What I Already Know

- The previous task added `WritingScore.analysis_payload` and report UI sections.
- The current implementation still has local template functions that create `overall_review`, `practice_focus`, `model_answer`, and paragraph coaching when the score payload does not include them.
- That is not acceptable for real reports: AI should decide paragraph logic, whether the essay can be mapped paragraph-by-paragraph, and what rewrite/advice belongs to each paragraph.
- If structure is too messy, AI should set a structure-advice-only result and explain how to repartition the answer.
- Saving unsegmented drafts should remain allowed.
- Scoring should still reject answers with no visible paragraph breaks.

## Requirements

- Keep the simple preflight requirement: answer must contain at least 2 paragraph blocks before AI scoring starts.
- Remove local hard-coded model-answer and paragraph-coaching generation from the `backend="ai"` path.
- Persist structured analysis only when the provider/AI result supplies it.
- If an AI result is missing structured report fields, reject completion instead of silently generating fake structured analysis.
- Fallback/local scoring may still produce an explicit fallback analysis payload, but it must be clearly marked as fallback and must not be presented as AI logical segmentation.
- Mock-success provider tests may emit deterministic structured payload, but that is test-only behavior.
- Preserve frontend report rendering contract.

## Acceptance Criteria

- [x] `backend="ai"` score completion requires AI-supplied `overall_review`, `practice_focus`, and either `paragraph_reviews` or `structure_advice_only + structure_advice`.
- [x] AI paragraph reviews are persisted exactly from payload, with learner text aligned only by explicit review rows.
- [x] Local code no longer creates hard-coded model paragraphs for AI results.
- [x] Fallback results are clearly fallback and do not masquerade as AI paragraph analysis.
- [x] Tests cover rejection of incomplete AI structured analysis.
- [x] Tests cover valid AI paragraph review payload persistence.
- [x] Existing writing/AI tests pass.
- [x] JS syntax still passes.

## Out of Scope

- Wiring a new real external writing provider.
- Changing report UI layout from the previous task.
- Removing the paragraph preflight modal.

## Technical Notes

- Main files: `backend_django/apps/writing/services.py`, `backend_django/apps/writing/tests.py`, `backend_django/apps/ai/provider_adapters.py`, `backend_django/apps/ai/tests.py`.
- The key risk is preserving worker tests while preventing fake AI analysis in production paths.
