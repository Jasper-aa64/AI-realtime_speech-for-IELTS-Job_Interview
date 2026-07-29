# P3 Natural Answer And Four Skills Design

## Goal

Make every P3 model-answer path follow one shared Band 7.5+ spoken-answer
standard, and simplify the P3 discussion-skills report from five dimensions to
four dimensions displayed in a stable 2x2 grid.

## P3 model-answer contract

The shared P3 constraint belongs beside `model_answer_constraints()` and is
consumed by the single-turn, batch-report, compact-retry, and legacy standalone
model-answer paths.

The answer:

- lasts roughly 45-70 seconds, normally about 90-140 English words;
- sounds like an unplanned but fluent conversation, not a written mini-essay;
- directly engages with the question, then develops a position through
  reason/background, a grounded observation, diplomatic qualification, and a
  light ending that leaves room for examiner follow-up;
- may use active listening or thinking-aloud language when natural, but must
  vary wording and must not mechanically prepend the same phrase;
- uses a China-context observation and a small personal lens when they are
  relevant and supportable, without inventing specific personal facts;
- preserves the learner's core idea and uses cautious language rather than
  overclaiming;
- returns only the spoken English answer. Reusable expressions remain marked by
  the existing Markdown bold convention; Chinese explanation remains in AI
  coaching so model-answer TTS never reads an appendix.

The selected target-band label remains unchanged. The shared contract raises
the P3 answer style and usefulness; it does not change scoring.

## P3 discussion-skills contract

New reports contain exactly these four dimensions:

1. `abstract_extension` - 抽象展开
2. `reasoning` - 原因与影响
3. `comparison_concession` - 对比让步
4. `specific_support` - 具体支撑

`follow_up_handling` is removed from heuristic output and AI enrichment input.
The report renderer also filters this legacy key so previously saved reports
show the same four-card layout.

Desktop and tablet use an explicit two-column grid. Narrow mobile uses one
column. No card changes height or column count because of status.

## Verification

- Prompt tests prove all P3 generation paths contain the shared natural-answer
  contract and keep answer-only/TTS-safe output.
- Backend tests prove generated and enriched P3 skill payloads contain exactly
  four dimensions.
- Frontend tests prove legacy `follow_up_handling` is hidden and the grid is
  explicitly 2x2.
- Run focused speaking tests, JavaScript syntax checks, and `git diff --check`.
