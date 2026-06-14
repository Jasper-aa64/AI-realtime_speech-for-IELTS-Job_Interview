# IELTS Speaking Sources

## Current Season Cache

- IELTSBro API latest cache dates: `p1Update 2026-05-22`, `p23Update 2026-06-10`.
- The local `.firecrawl/ieltsbro-api/` cache remains a useful cross-check when present, but it is not required for a fresh clone to validate seed contents.

## Retained P1 Source

- Primary source file: `data/ielts/sources/2026_may_august_ielts_speaking_bank_0604.pdf`.
- Companion text layer: `data/ielts/sources/2026_may_august_ielts_speaking_bank_0604.txt`.
- PDF details: 50 pages, WPS-created, created on `2026-06-04`.
- This PDF is the retained main source for `data/ielts/part1/2026_may_august_retained_topics.json`.
- Questions were extracted from the PDF text layer with local `pdftotext` style parsing and minimal cleanup only.

## idictation (爱听写 / 神奇题库) Current-Season Part 1 Bank

- Source file: `data/ielts/sources/2026_may_august_idictation_part1_bank.json` (37 topics, scraped 2026-06-14 via a logged-in topic sweep of `https://www.idictation.cn/`).
- This is the **authoritative base** for the merged P1 seed files. The 2026 May–August retained and new topic files were rebuilt as: idictation base, with genuinely-distinct questions from the 0604 PDF / public season lists topping up only the thin (<8 question) topics, deduplicated by Jaccard similarity (>=0.55 dropped) to avoid paraphrase bloat.
- Topics present in neither the idictation current season nor the 0604 PDF were moved to `data/ielts/archive/old_topics.json`.

## Notes

- Firecrawl quota was insufficient for this pass, so local PDF text parsing was used instead.
- AiTingxie/Chrome login was not needed for this pass; it can be used later for cross-checking if needed.
- 老烤鸭 was not used as the primary source because the WPS PDF is fuller and season-specific; it remains a future spot-check source.
- `data/ielts/archive/old_topics.json` remains an archive/source bucket and should not affect current-season loading.
