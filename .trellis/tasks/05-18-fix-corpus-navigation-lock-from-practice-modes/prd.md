# Fix Corpus Navigation Lock From Practice Modes

## Goal

Make navigation from P1/P2/P3/Mock practice modes to `语料库` reliable, even when a practice session has already locked the sidebar.

## Root Cause

When `state.practiceLocked` is true, the sidebar click handler blocks every navigation target except the current view and only shows a lock hint. This is correct for most mode switches, but it makes the corpus entry feel stuck when users try to leave practice and manage materials.

## Requirements

- Clicking `语料库` from a locked practice view should exit/abort the current practice runtime, then switch to the corpus landing page.
- Keep the existing lock behavior for switching between practice modes during an active attempt.
- Do not address the separate new-window behavior in this task.
- Preserve cleanup semantics: timers/audio/recording should stop via the existing exit path.

## Acceptance Criteria

- [x] From a locked P1/P2/P3/Mock state, clicking `语料库` no longer only shows the lock toast.
- [x] The current attempt is aborted through the existing exit path before switching.
- [x] The UI lands on `corpus`.
- [x] Practice-mode switching remains locked during active practice.
- [x] JS syntax check passes.

## Technical Notes

- Main file: `web/static/app.js`.
- Current click handler is in `bindEvents()`.
- Existing cleanup path: `exitPractice()`.
