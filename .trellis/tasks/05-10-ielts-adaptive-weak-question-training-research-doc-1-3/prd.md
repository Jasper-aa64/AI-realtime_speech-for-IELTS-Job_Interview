# IELTS adaptive weak-question training research doc 1.3

## Goal

Write a standalone research document for an adaptive IELTS practice feature that continuously revisits the question bank, stores low-scoring or misunderstood answers, increases the replay frequency of weak items, and marks questions as weak with statistical support rather than ad hoc heuristics.

## What I already know

* The current IELTS web app already stores attempts, turns, scores, history, and per-turn reports.
* Current question selection is mostly random sampling from Part 1 and Part 2 banks, with some adaptive follow-up logic only for P3 and P1 identity follow-ups.
* There is no item-level adaptive scheduler, no weak-question registry, and no statistical model for mastery or difficulty.
* The current local corpus is too sparse to calibrate weak-item logic directly: history attempts exist, but most turns lack transcript and therefore cannot support reliable learning analytics.
* A serious solution should use psychometric / learner-modeling ideas such as IRT, Bayesian knowledge tracing, and spaced repetition / bandit-style scheduling, not a simple “low score = show more” rule.

## Assumptions (temporary)

* "低分" should mean a combination of low band score, low relevance, and low confidence / high uncertainty, not only a single total score.
* "没理解题目意思" should be modeled explicitly as an off-topic or low-relevance signal, separate from language quality.
* The final document should be a standalone markdown file in `docs/` with version `1.3` in the title.

## Open Questions

* None blocking. The feature can be specified without additional user input.

## Requirements (evolving)

* Define a non-toy statistical model for item weakness, user ability, and replay frequency.
* Explain how to store and label low-quality answers.
* Distinguish between one-off bad answers and persistent weak items.
* Include a replay policy with mathematical support for frequency control and exposure fairness.
* Tie the research back to the current IELTS repo architecture and data model.

## Acceptance Criteria (evolving)

* [x] A standalone markdown document exists under `docs/` with version `1.3` in the title.
* [x] The document defines weak items using statistical criteria, not manual tags alone.
* [x] The document proposes a mathematical model for replay frequency and item difficulty.
* [x] The document includes source links to primary research on IRT, BKT, bandits, or spacing effects.
* [x] The document explains how low-score and off-topic answers are stored and reused safely.
* [x] The document ends with practical implementation guidance for the current repo.

## Definition of Done

* Research notes are captured in the task directory.
* Final markdown document is written and reviewed for coherence.
* Source links are present and clearly attributed.

## Out of Scope

* No code changes in this task.
* No training of new ML models in the repo.
* No claim that the resulting scheduler is an exam-grade scoring system.

## Technical Notes

* Current question selection is in `web/ielts_server.py` through `QuestionBank.sample()` and `build_p1_turns()`.
* Current history/report storage is in `reports/attempts/`.
* Current web UI history/report rendering is in `web/static/app.js`.
* Relevant local task docs: `docs/IELTS_CHINA_SCORING_STANDARD_1_1.md` and prior IELTS web tasks in `.trellis/tasks/05-09-*`.
* Primary research candidates:
  * `https://arxiv.org/abs/2108.08604`
  * `https://arxiv.org/abs/1803.05926`
  * `https://arxiv.org/abs/1707.02038`
  * `https://pubmed.ncbi.nlm.nih.gov/16719566/`
  * `https://doi.org/10.1007/BF01099821`
