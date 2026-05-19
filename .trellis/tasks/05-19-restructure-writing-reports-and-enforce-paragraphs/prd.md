# Restructure Writing Reports And Enforce Paragraphs

## Goal

Bring writing reports closer to speaking reports: prompt card first, then an "Overall Review & Practice Focus" block, then repeated paragraph review groups containing the learner paragraph, an AI/model rewrite, and coaching. Also reject AI scoring when the answer is not paragraph-separated.

## Scope

- Add paragraph validation before AI scoring/synchronous scoring.
- Allow saving unsegmented drafts, but block AI analysis until paragraphing is fixed.
- Add task-specific paragraphing guidance for Task 1 and Task 2.
- Surface guidance in a frontend modal before submitting scoring.
- Add structured writing report payload fields:
  - overall review
  - practice focus
  - model answer
  - per-paragraph review rows
  - structure-advice-only mode when the paragraph structure is too messy to map reliably
- Rework writing report detail layout:
  - prompt card on top, using the same bordered style as the prompt screenshot
  - score/overall review section
  - paragraph groups with "我的原文" / "AI 写法" / "AI 辅导"
  - or a paragraph-structure advice block when AI cannot reliably map paragraph-by-paragraph feedback
- Let users open the report entry back in the writing editor to revise and regenerate the report.
- Keep existing score and feedback markdown fallback-compatible.

## Acceptance Criteria

- [x] Saving an unsegmented answer is still allowed.
- [x] AI scoring rejects an answer with fewer than 2 paragraph blocks.
- [x] Task 1 rejection guidance explains Task 1 paragraphing.
- [x] Task 2 rejection guidance explains Task 2 paragraphing.
- [x] Frontend shows a modal instead of silently submitting bad paragraphing.
- [x] Backend rejects direct score-task requests for unsegmented answers.
- [x] Writing report starts with the prompt card.
- [x] Writing report includes "Overall Review & Practice Focus", "总体点评", and "复盘重点".
- [x] Report renders paragraph groups: learner paragraph, AI rewrite, AI coaching.
- [x] Messy paragraph structure can render paragraph revision advice instead of forced paragraph mapping.
- [x] Report provides an edit/regenerate entry point.
- [x] Existing writing tests pass.
- [x] JS syntax check passes.
