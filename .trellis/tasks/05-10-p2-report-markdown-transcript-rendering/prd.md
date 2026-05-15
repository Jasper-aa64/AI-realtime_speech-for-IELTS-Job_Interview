# P2 Report Markdown Transcript Rendering

## Goal

Make IELTS Speaking Part 2 report detail easier to compare by formatting both the candidate transcript and Band 7 spoken version as safe, paragraph-preserving Markdown, while closing the existing raw HTML injection risk in the frontend Markdown renderer.

## What I Already Know

* The user explicitly accepts that P1/P3 can skip preparation; this task must not change that behavior.
* Backend report data is generated in `web/ielts_server.py`.
* Frontend report rendering and `renderMarkdown` live in `web/static/app.js`.
* Existing report compatibility matters: old reports may only have `transcript_cleaned` and `band7_version`.
* Pronunciation behavior must not change.

## Requirements

* For P2 report detail, expose Markdown-ready candidate transcript text and Band 7 spoken version text, using readable paragraphs/sections where appropriate.
* Update the P2 model answer prompt path so AI-generated Band 7 answers request concise Markdown paragraphs and return only answer text.
* Keep legacy report fallback behavior in the frontend.
* Make `renderMarkdown(value)` safe by escaping HTML before applying a small Markdown subset.
* Supported Markdown subset: `**bold**`, `*italic*`, inline `` `code` ``, and paragraph/line breaks.
* Avoid raw HTML injection and avoid fragile nested Markdown behavior where practical.

## Acceptance Criteria

* [ ] Scored P2 turns include Markdown-ready transcript/model fields or preserve paragraph output in existing fields.
* [ ] Report detail cells render candidate transcript and Band 7 version with safe Markdown formatting.
* [ ] Raw HTML in rendered Markdown is escaped, not executed.
* [ ] Existing reports fall back to `transcript_cleaned` and `band7_version`.
* [ ] Pronunciation scoring/audio behavior is unchanged.

## Definition of Done

* `node --check web/static/app.js`
* `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py`
* `python3 -m unittest discover -s tests -p 'test_*.py'`

## Out of Scope

* Changing P1/P3 preparation behavior.
* Changing pronunciation behavior.
* Broad report UI redesign outside the affected report text cells.
* Committing changes.

## Technical Notes

* Relevant search terms: `renderMarkdown`, `band7_version`, `transcript_cleaned`, `model_answer_with_codex`.
