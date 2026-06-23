# P2 Brainstorm Copy Requirements Design

## Goal

When copying the current Brainstorm filter result, include each question's cue-card requirements as well as its live, possibly unsaved brainstorm text.

## Output Contract

Each copied block uses this shape:

```text
1. Describe ...
    - bullet 1 - bullet 2 - bullet 3  And explain ...
    灵感：...
```

The requirements line and brainstorm line begin with exactly four ASCII spaces. Multiple blocks remain separated by one blank line. Existing filter behavior is unchanged.

## Data Flow

The copy handler resolves each visible DOM row back to its current P2 card entry. A pure formatter combines the visible row number and title with the entry's `bullets` and `rounding` fields and the live brainstorm input value. If structured requirements are absent, it uses the question text remaining after the cleaned title.

## Verification

A Node regression test loads the frontend controller and calls the pure formatter directly. It asserts the exact copied string, including indentation, bullet order, rounding text, and brainstorm text.
