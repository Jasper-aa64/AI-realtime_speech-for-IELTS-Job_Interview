# IELTS China scoring standard research doc 1.1

## Goal

Produce a standalone research document that explains how IELTS Speaking should be interpreted for the China context, clarifies that China follows the global IELTS speaking rubric rather than a separate domestic scoring formula, and records sample-driven observations that can guide the simulator's AI coaching and scoring wording.

## What I already know

* Official IELTS Speaking uses 3 parts, 11-14 minutes, and 4 equal criteria: Fluency and Coherence, Lexical Resource, Grammatical Range and Accuracy, and Pronunciation.
* IELTS China / British Council China materials state that IELTS and Aptis were aligned with the China Standards of English (CSE), so the local reference layer is Chinese-facing, not a different scoring system.
* The Chinese official speaking band descriptor PDF exists and says the English version is authoritative; the Chinese translation is reference-only.
* The China mainland 2024-2025 data report says speaking remains a key bottleneck and that oral skill is highly valued for study and work use cases.
* The current repo has a small local IELTS sample corpus: 9 Part 1 JSON files, 2 Part 2 JSON files, and 3 attempt reports, many of which are fallback-heavy and transcript-light.

## Assumptions (temporary)

* "符合中国的雅思评分标准" means: use the official IELTS speaking rubric, then explain it in the China-localized language and CSE-aligned framing used by Chinese official materials.
* The deliverable should be a standalone markdown document in `docs/`, not just a task note.

## Open Questions

* None blocking. The document can proceed with the above assumption.

## Requirements (evolving)

* Write a separate `1.1` research document for the China-specific scoring context.
* Distinguish clearly between official global IELTS rules and China-localized explanation layers.
* Include sample-based findings from official IELTS sources, China official sources, and the current project corpus.
* Call out what is inference versus what is directly supported by sources.
* End with concrete product implications for the simulator's scoring, coaching, and sample bank design.

## Acceptance Criteria (evolving)

* [x] A standalone markdown document exists under `docs/` with version `1.1` in the title.
* [x] The document explains that China does not have a separate scoring scale, only a localized explanation/mapping layer.
* [x] The document includes at least 5 source links, including official IELTS and China IELTS / British Council China sources.
* [x] The document includes sample observations from both official research and the local repo sample corpus.
* [x] The document ends with a short implementation-oriented recommendation list.

## Definition of Done

* Research notes are captured in the task directory.
* Final markdown document is written and reviewed for consistency.
* Source links are present and clearly attributed.

## Out of Scope

* No code changes in this task.
* No attempt to invent a China-only numeric band system.
* No training of models or generation of new audio assets.

## Technical Notes

* Official IELTS Speaking format: `https://ielts.org/take-a-test/test-types/ielts-academic-test/ielts-academic-format-speaking`
* IELTS scoring detail: `https://ielts.org/take-a-test/your-results/ielts-scoring-in-detail`
* Official China band descriptor translation PDF: `https://backoffice.ielts.chinaielts.org/api/assets/ielts-cms/26ab0d00-d846-44e9-ad76-253d064ce623/uobds-speakingfinal.pdf`
* British Council China CSE alignment page: `https://www.britishcouncil.cn/exams/cse/results`
* China mainland 2024-2025 data report: `https://www.chinaielts.org/press-office/IELTS-%20Chinese-Mainland%20-Big-Data-Report-2024-2025`
* Local sample corpus: `data/ielts/part1/`, `data/ielts/part2/`, `reports/attempts/`
