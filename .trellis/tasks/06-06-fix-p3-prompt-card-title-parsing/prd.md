# Fix P3 Prompt Card Title Parsing

## Problem

In the P2 corpus / P3 follow-up UI, the P3 dialog and card title sometimes use the entire cue-card text as the title. This incorrectly includes bullet prompts such as "What the news was about", "Where you heard or read it", and "And explain...".

## Goal

Render the P2 cue card with a clean title:

- Title: only the main cue-card instruction, e.g. `Describe a piece of local news that interested you`
- Bullets: shown separately in the body
- Rounding sentence: shown separately in the body

The P3 dialog title must not include bullet prompts or the final "And explain..." sentence.

## Scope

- Frontend parsing/rendering only.
- Keep the existing bank corpus / personal corpus distinction.
- No database or API changes unless the existing payload requires normalization in the browser.

## Acceptance

- P2 card and P3 modal no longer duplicate bullet text in the title.
- `node --check web/static/corpus-takeaway.js` passes.
- `node --check web/static/app.js` passes if touched.
