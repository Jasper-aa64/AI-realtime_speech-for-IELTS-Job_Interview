# China IELTS scoring standard research notes

## Baseline: official IELTS speaking rules

* Speaking is face-to-face, recorded, and split into 3 parts.
* Time allowed is 11-14 minutes.
* The four criteria are weighted equally.
* Part 1 is everyday familiar topics, Part 2 is a 1-minute prep + 2-minute long turn, and Part 3 is a deeper discussion on the Part 2 topic.
* Overall score is the average of the section scores, rounded to the nearest half band.

## China-localized layer

* British Council China states that IELTS and Aptis were aligned with the China Standards of English (CSE).
* The Chinese official speaking descriptor PDF is a translation reference; it says the English version is authoritative.
* This means the app should not invent a new "China band scale"; it should keep the IELTS rubric and localize the explanation layer for Chinese users.

## Sample research sources reviewed

* IELTS speaking format page, for the official task structure and timing.
* IELTS scoring detail page, for the overall rounding rule and equal weighting.
* Official Chinese speaking band descriptor PDF, for Chinese-language rubric wording and local interpretation.
* British Council China CSE alignment page, for the local standards framing.
* China mainland 2024-2025 data report, for Chinese candidate demand and the importance of speaking.
* IELTS research reports on speaking features, pronunciation, lexical resource, and Chinese/interlanguage-related pronunciation studies, for evidence about what differentiates bands.

## Local repo sample notes

* `data/ielts/part1/` currently contains 9 topic files and 60 questions.
* `data/ielts/part2/` currently contains 2 topic files and 15 cue-card topics.
* `reports/attempts/` currently contains 3 sample attempts and 53 turns.
* Current attempt reports are heavily fallback-oriented:
  * 53/53 turns have missing transcripts,
  * some coaching is generic,
  * some scoring paths fall back when the CLI is unavailable.

## Interpretation for the document

* "China scoring standard" should be described as: global IELTS rubric + China-localized explanation + CSE mapping + Chinese learner calibration examples.
* The most useful research sample classes are:
  * official descriptor samples by band,
  * official speaking-format samples by part,
  * China-facing official materials,
  * local project report samples.
