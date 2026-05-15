# P1 Report And Audio Fix Plan

## Goal

Implement the requested IELTS web behavior changes for examiner audio, P1 Band 7 fallbacks, AI coaching format, structured overall review rendering, and P1 work/study completion latency.

## What I Already Know

- Scope is limited to `web/ielts_server.py`, `web/static/app.js`, `web/static/styles.css`, `tests/test_ielts_web_server.py`, and relevant `.trellis/spec` docs.
- Latest user correction: examiner practice questions should keep the existing audio URL first path rather than forcing browser speech synthesis.
- Generated model-answer audio should remain only for Band 7 playback, with existing browser fallback when unavailable.
- `/complete` must preserve deterministic P1 work/study follow-up insertion without synchronous Codex or external TTS calls.
- Current specs mention fixed report/coaching rendering expectations that conflict with the requested freer Chinese coaching format.

## Requirements

- Keep existing examiner audio playback behavior: use generated audio URL when available, with browser fallback only when unavailable.
- Tighten `turn_feedback_with_codex` so Band 7 answers the exact question, reuses candidate intent, keeps P1 to 1-3 natural spoken sentences, and rejects generic template lines.
- Replace `build_turn_band7_fallback` with question-aware P1 fallbacks for common question types.
- Fall back when Codex Band 7 output is generic or misses key question intent.
- Request concise Chinese Markdown coaching in freer format: 2-4 short bullets or a short paragraph plus one example sentence, with concrete correction and usable replacement sentence but no fixed labels.
- Make deterministic coaching fallback short, varied, natural, and question-relevant.
- Render `overall_review` from `comment` and `review_points` in the frontend review card; ignore `overall_review.markdown` for that card.
- Update backend/frontend quality guidelines so future work does not restore forced coaching labels.

## Acceptance Criteria

- [ ] P1 work/study completion returns deterministic follow-up and does not synchronously call Codex.
- [ ] P1 Band 7 fallback does not contain "quite easy for me to answer" and is question-aware.
- [ ] Coaching fallback does not require fixed labels and remains concise.
- [ ] Overall review supports structured `comment` and `review_points`; frontend ignores `markdown` for the dedicated card.
- [ ] Focused unittest passes.
- [ ] `py_compile` and `node --check` pass.

## Out of Scope

- Broad report redesigns.
- Changes outside the listed ownership files.
- Removing generated model-answer audio for Band 7 playback.
