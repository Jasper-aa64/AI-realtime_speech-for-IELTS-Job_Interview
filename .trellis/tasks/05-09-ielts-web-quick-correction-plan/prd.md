# IELTS Web quick correction plan

## Goal

Improve the IELTS Web practice and report flow by cleaning up active-practice audio UI, making scoring feedback obvious, adding high-intensity dynamic P3 generation, tightening report/history behavior, and extending tests around attempt validity and scoring output contracts.

## Requirements

- Practice UI hides candidate playback during active practice and hides examiner TTS controls for P1/P3 while retaining status text.
- P2 keeps a stable left/right layout after start across listening, preparing, recording, scoring, and summary states.
- Scoring removes the global busy text and instead shows an orange animated Chinese scoring indicator near the recorder/voice control.
- Completed scoring auto-scrolls to the report/summary area and briefly highlights it.
- Dynamic prompt font remains capped at 42px desktop and 32px mobile.
- Report table header changes from `升级了什么` to `AI 辅导`.
- Backend persists `turn.ai_coaching` for each scored turn, with compatibility fallback from old `upgrade_notes`.
- Generated coaching, Band 7 text, and related report text are cleaned of Trellis/session/workflow/system-log contamination.
- Standalone P3 asks for topic input/chips before start, defaults to high intensity, generates from topic via model path when available, and records generation status/source.
- High-intensity P3 produces 5 main questions plus one adaptive follow-up per answer for 10 turns before one report.
- Mock P3 is generated after the P2 answer from cue card plus P2 answer, then uses the same high-intensity flow.
- History excludes incomplete, aborted, and unscored attempts.
- After a new P1 report is scored, older P1 report files are deleted so only the latest P1 remains.
- History top rail has visible horizontal-scroll affordance, title `Recent attempts`, hint `Swipe or use arrows to browse`, arrow buttons, fade edges, and active card state while details remain full width.

## Acceptance Criteria

- [ ] Active practice panel no longer shows candidate audio controls.
- [ ] P1/P3 examiner audio autoplays without visible controls/progress in the practice panel.
- [ ] P2 DOM/layout remains stable left/right after start.
- [ ] Scoring indicator uses the requested Chinese text and orange animation near the voice control.
- [ ] Scoring completion scrolls to and highlights summary/report.
- [ ] Report turns include `band7_version` and `ai_coaching`.
- [ ] Standalone P3 uses topic/free-text generation rather than bank defaults and follows 10-turn high-intensity flow.
- [ ] Mock P3 is generated after P2 answer when feasible and records `p2_answer` generation source.
- [ ] Invalid/unscored attempts stay out of history; aborted attempts cannot score.
- [ ] P1 scoring deletes older P1 reports.
- [ ] Required JS, Python compile, and unit test commands pass.

## Out of Scope

- Rewriting the whole practice state machine.
- Introducing frontend frameworks or new third-party browser dependencies.
- Touching unrelated dirty/untracked files listed by the user.

## Technical Notes

- Owned files: `web/static/app.js`, `web/static/index.html`, `web/static/styles.css`, `web/ielts_server.py`, `tests/test_ielts_web_server.py`.
- Follow `.trellis/spec/frontend/quality-guidelines.md`, `.trellis/spec/frontend/component-guidelines.md`, `.trellis/spec/backend/quality-guidelines.md`, and shared thinking guides.
