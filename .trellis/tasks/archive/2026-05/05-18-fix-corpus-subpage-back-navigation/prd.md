# Fix Corpus Subpage Back Navigation

## Goal

Make the top-left back button in corpus subpages behave as a corpus-level back action, not a practice-level return action.

## Requirements

- The button label should be `返回`, not `返回练习`.
- The button title and aria-label should also say `返回`.
- From `我的 P1语料库`, `我准备的P2串题素材库`, and `生词本`, clicking back should return to `语料库`.
- Keep standalone opened corpus windows behavior if still relevant.

## Acceptance Criteria

- [x] Back button visible on P1 corpus, P2 corpus, and takeaway book says `返回`.
- [x] Clicking it from any of those pages switches to `corpus`.
- [x] It no longer jumps back to P1/P2 practice modes.
- [x] JS syntax check passes.

## Technical Notes

- Main files: `web/static/index.html`, `web/static/app.js`.
- Current function: `closeCorpusWindowOrReturn()`.
