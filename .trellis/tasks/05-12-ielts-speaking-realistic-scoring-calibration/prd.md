# IELTS Speaking Realistic Scoring Calibration

## Goal

Improve IELTS Speaking practice scores so they stay anchored to official IELTS Speaking band descriptors while feeling closer to real China-region candidate outcomes.

## Requirements

- Use official IELTS Speaking criteria as the only scoring standard: Fluency and Coherence, Lexical Resource, Grammatical Range and Accuracy, Pronunciation.
- Do not create a separate "China score" or hidden regional penalty.
- Add a China-candidate realism calibration layer that makes 6.5+ and 7.0+ harder unless the transcript provides clear evidence.
- Penalize or cap scores for evidence that real examiners commonly punish:
  - off-topic or weak task coverage
  - very short answers, especially Part 2 and Part 3
  - generic memorized/template-sounding content
  - repeated simple vocabulary and filler-heavy answers
  - grammar that is mostly simple sentence forms
  - Part 3 answers without reasons, comparison, examples, or abstract development
- Do not infer pronunciation from text. If no real audio pronunciation assessment exists, keep pronunciation as null and apply conservative uncertainty calibration instead of inventing a pronunciation band.
- Preserve existing API contracts and report shape.

## Implementation Plan

- Update `data/ielts/prompts/scorer_system.md` with stricter official-rubric calibration instructions.
- Add deterministic post-processing in `web/ielts_server.py` after Codex and fallback scoring.
- Keep off-topic caps stronger than general calibration caps.
- Add unit tests for short/generic answer caps, missing-pronunciation uncertainty, and Codex score post-processing.

## Acceptance Criteria

- `python -m py_compile web/ielts_server.py tests/test_ielts_web_server.py` passes.
- `python -m unittest tests.test_ielts_web_server` passes.
- Short/generic answers cannot receive inflated 6.5+ practice scores.
- Missing pronunciation assessment is clearly not converted into a fake pronunciation score.
- Prompt and code both state that official IELTS rubric remains the scoring baseline.
