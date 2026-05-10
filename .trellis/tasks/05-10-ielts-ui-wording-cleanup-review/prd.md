# IELTS UI wording cleanup review

## Goal
Review the current IELTS web UI wording after the natural-language cleanup and fix small wording or syntax issues in `web/ielts_server.py` and `web/static/app.js`.

## Scope
- Confirm the China explanation still says scoring follows the official IELTS Speaking rubric.
- Keep visible Chinese natural and non-awkward.
- Check for obvious garbled placeholder strings or broken template literals.
- Run `node --check web/static/app.js` and `python -m py_compile web/ielts_server.py`.

## Non-goals
- No scoring model changes.
- No broad UI redesign.
