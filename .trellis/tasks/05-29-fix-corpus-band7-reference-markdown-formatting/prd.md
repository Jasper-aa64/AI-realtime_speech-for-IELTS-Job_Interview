# Fix Corpus Band 7 Reference Markdown Formatting

## Goal

Fix the P1 corpus editor's "7分回答参考" display so AI-generated Band 7 Markdown renders as natural spoken paragraphs. Bold Markdown phrases should stay inline instead of being broken onto separate lines, while copy behavior should still preserve the original Markdown source.

## What I Already Know

* The dialog HTML lives in `web/static/index.html`.
* The P1 corpus editor fills `#p1CorpusAiAnswer` in `web/static/app.js`.
* The shared `renderMarkdown()` helper currently turns single newlines inside paragraphs into `<br>`.
* The problematic AI answer contains soft line breaks around emphasized phrases, which makes the UI render awkward line breaks and standalone punctuation.
* The fix should not rewrite the stored answer or broadly change all report Markdown rendering.

## Requirements

* The "7分回答参考" block should render soft line breaks inside normal prose as spaces.
* Markdown emphasis such as `**a relaxed vibe**` should render inline.
* Blank lines should still create paragraph breaks.
* Bulleted/numbered lists should remain readable.
* Copying the answer should still copy the Markdown source, not the normalized HTML display.

## Acceptance Criteria

* [ ] The shown example renders as natural paragraphs, not one phrase per line.
* [ ] Bold phrases remain visibly emphasized inline.
* [ ] No extra standalone comma/period lines appear from soft line breaks.
* [ ] `node --check web/static/app.js` passes.

## Out of Scope

* Changing AI prompt generation.
* Changing stored corpus data.
* Reworking the P1 corpus editor layout.
