# Repair corrupted IELTS Chinese guidance text

## Goal

Fix the visible `????` placeholders in the IELTS web server and web UI so the report reads naturally for users.

## Scope

- `web/ielts_server.py`
- `web/static/app.js`

## Requirements

- Replace corrupted user-visible strings in `build_china_explanation()` with natural Chinese guidance text.
- Replace corrupted user-visible strings in the frontend report rendering with readable Chinese / English labels.
- Keep the official IELTS Speaking rubric as the scoring source.
- Keep `china_explanation` as a Chinese guidance layer only, not a separate score system.
- Preserve the intended wording patterns:
  - `中文说明`
  - `常见短板`
  - `下一步`
  - human fallback text
  - `Pron` / `Estimate` where appropriate
- Do not change `web/static/styles.css` unless a tiny adjacent fix is truly unavoidable.

## Acceptance Criteria

- No visible `????` remain in user-facing strings in the two target files.
- `node --check web/static/app.js` passes.
- `python -m py_compile web/ielts_server.py` passes.
- The explanation content still points to IELTS rubric-based scoring and Chinese learner guidance.

