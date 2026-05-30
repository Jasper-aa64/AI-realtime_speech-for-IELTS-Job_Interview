# Add Current Speaking Season Bank To Account Profile

## Goal

Add a visible speaking question-bank selector to the account profile page above the dark appearance control, so learners can choose which bank powers practice and corpus views.

## What I Already Know

- User clarified that this should be a `题库选择` control, not only a static `当季题库` card.
- User clarified that non-current seasons are not discarded; they remain as usable history.
- User clarified that prepared corpus should be shared by original question/cue, so retained questions do not lose previous season material.
- User wants the control positioned above `深色外观` in the account profile page.
- Current season backend metadata exists in `/api/question-bank/summary`.
- Existing account page already has profile/wallet/training card styling.

## Requirements

- Show `题库选择` in the left account/profile card above dark appearance.
- Provide five scopes: `当前考季`, `新题`, `保留题`, `历史考季`, `全部题库`.
- Display active season, P1 count, P2 count, and P3 derived-from-P2 status for the selected scope.
- Persist selected scope in browser storage.
- Selected scope must affect P1/P2 practice sampling and P1/P2 corpus metadata, not just the account page label.
- P1 corpus must use a canonical question id independent of topic/season, with legacy id fallback.
- P2 corpus saves linked cue material under a stable id when linked to a cue prompt.
- Extend existing question bank APIs with a `scope` parameter; no database migration.
- If unauthenticated or API fails, show a concise fallback instead of breaking account page.

## Acceptance Criteria

- [x] Account profile page shows `题库选择` above `深色外观`.
- [x] The selector displays 2026 May-Aug current season counts from `/api/question-bank/summary`.
- [x] Selecting `新题`, `保留题`, `历史考季`, or `全部题库` updates summary and is persisted.
- [x] P1/P2 practice start sends the selected scope to Django.
- [x] P1/P2 corpus GET requests use the selected scope.
- [x] Retained questions can reuse material saved under a previous topic/season id.
- [x] Django tests cover summary/sample/start/corpus scope behavior.
- [x] `node --check web/static/app.js` passes.

## Out of Scope

- Per-user server-side preference persistence.
- Changing corpus editor behavior.
