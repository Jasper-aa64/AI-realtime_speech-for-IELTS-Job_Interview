# IELTS report and default candidate adjustments

## Goal

Improve the IELTS Web report experience and defaults: use `jasper` as the candidate default, generate question-specific AI coaching, show mock reports with clear part-level scores, and replace live-generated criteria advice with static IELTS reference guidance.

## Requirements

- Settings candidate name defaults to `jasper`.
- Starting an attempt without an explicit candidate uses `jasper`, not `web-user`.
- Per-question `AI 辅导` is specific to the question, candidate transcript or cleaned transcript, and Band 7 spoken version.
- Prefer existing backend AI/Codex mechanisms for coaching; deterministic fallback must compare the original answer with the Band 7 version and must not emit the same generic template for every row.
- Mock reports display Overall at the top, then Part scores for P1/P2/P3 with Band and FC/LR/GRA/Pronunciation summaries.
- Mock question details remain readable and must not appear as an undifferentiated block of 21 questions.
- Standalone P1/P2/P3 reports keep clear Overall scoring at the top.
- Rename `各维度评分` to `📊 参考：雅思各维度评分标准，以及提升建议`.
- Criteria guidance is static IELTS dimension reference content, not generated live by AI.
- FC/LR/GRA/Pronunciation each show standard explanation and band-range-specific improvement suggestions.
- If Pronunciation is not assessed, report that clearly as `Pronunciation not assessed` / Azure not configured.
- Mock report shows the criteria reference once at the end, not after each part.
- Update `tests/test_ielts_web_server.py` for defaults, coaching fallback specificity, part scores, and backend-testable criteria fields.

## Acceptance Criteria

- [ ] `node --check web/static/app.js` passes.
- [ ] `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py` passes.
- [ ] `python3 -m unittest discover -s tests -p 'test_*.py'` passes.
- [ ] No unrelated files are modified.
- [ ] No git commit is created.

## Technical Notes

- Scope is expected to include `web/ielts_server.py`, `web/static/app.js`, and `tests/test_ielts_web_server.py`.
- Follow frontend and backend Trellis specs for IELTS Web UI API contracts, deterministic fallbacks, and readable report rendering.
