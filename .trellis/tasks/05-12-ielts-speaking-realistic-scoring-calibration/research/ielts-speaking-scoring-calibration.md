# IELTS Speaking Scoring Calibration Research

## Sources

- IELTS official Speaking format page: confirms the test uses three parts and four assessment criteria considered by examiners.
- IELTS official Speaking band descriptors PDF / scoring detail page: confirms Speaking scores are based on Fluency and Coherence, Lexical Resource, Grammatical Range and Accuracy, and Pronunciation, with equal weighting.
- China IELTS official 2024-2025 mainland big data report and China Daily coverage: mainland Academic IELTS overall average was reported around 5.9, with Speaking/Writing remaining common bottlenecks for Chinese mainland candidates.
- Informal Chinese-language social feedback from Zhihu/Reddit/Xiaohongshu-style discussions clusters around "口语 5.5/6.0/压分" complaints. The useful signal is not a formal scoring rule, but recurring failure patterns: memorized templates, answers that sound recited rather than interactive, Part 2 running out of content, Part 3 lacking analysis, direct translation, simple grammar, and repeated generic words.

## Product Interpretation

There is no separate China-region IELTS Speaking rubric. The backend must not invent a regional score. Calibration should instead make the practice system less optimistic where transcripts show patterns that real IELTS examiners are likely to score conservatively.

## Calibration Rules To Encode

- Keep official four-criterion scoring as the model prompt baseline.
- Do not award Band 7 unless the transcript shows sustained development, natural cohesion, flexible vocabulary, and frequent controlled sentences.
- Treat 5.5/6.0 as common realistic outcomes for understandable but thin answers.
- Cap Part 2 short answers because the real long turn expects sustained speech and cue-card coverage.
- Cap Part 3 answers without reasoning/comparison/examples because the part tests abstract discussion.
- Cap generic template-heavy answers even when they are fluent-looking.
- If pronunciation is not assessed from audio, do not fill it from transcript; keep it null and prevent the three text dimensions from inflating the overall too far.
