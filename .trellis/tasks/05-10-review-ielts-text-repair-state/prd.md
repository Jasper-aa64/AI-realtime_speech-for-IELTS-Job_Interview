# Review IELTS text repair state

## Goal

Review the current IELTS Web UI/backend text state after the text-repair request, focusing only on `web/ielts_server.py` and `web/static/app.js`.

## Checks

- No visible `????` or garbled placeholders remain in user-facing strings.
- China explanation clearly states that the official IELTS Speaking rubric is the single score source.
- `renderSummary`, `renderDetail`, and `chinaExplanationBlock` show natural labels and fallback text.
- No syntax breakage or accidental label corruption remains.

## Verification

- `node --check web/static/app.js`
- `python -m py_compile web/ielts_server.py`
