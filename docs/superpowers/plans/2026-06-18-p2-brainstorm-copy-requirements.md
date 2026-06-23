# P2 Brainstorm Copy Requirements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Include P2 cue-card requirements in Brainstorm clipboard output using the user's exact four-space-indented format.

**Architecture:** Add one pure formatter to `corpus-takeaway.js`, expose it beside the existing controller for direct unit testing, and make the current copy handler feed it the visible row plus its backing P2 card. Filtering and clipboard transport remain unchanged.

**Tech Stack:** Browser JavaScript, Node.js built-in test runner.

---

### Task 1: Lock and implement the clipboard format

**Files:**
- Create: `scripts/test_p2_brainstorm_copy_format.mjs`
- Modify: `web/static/corpus-takeaway.js:3926-3946`

- [x] **Step 1: Write the failing test**

Create a Node test that loads `corpus-takeaway.js`, calls `formatP2BrainstormCopyBlock`, and expects the exact three-line block with four-space indentation.

- [x] **Step 2: Run the test to verify it fails**

Run: `node --test scripts/test_p2_brainstorm_copy_format.mjs`

Expected: FAIL because `formatP2BrainstormCopyBlock` is not exported yet.

- [x] **Step 3: Write the minimal implementation**

Add the pure formatter, expose it on `window.IELTSCorpusTakeaway`, and replace the copy handler's title-plus-idea string assembly with the formatter using the row's backing P2 entry.

- [x] **Step 4: Run focused and project verification**

Run:

```powershell
node --test scripts/test_p2_brainstorm_copy_format.mjs
node --check web/static/corpus-takeaway.js
python backend_django/manage.py check
git diff --check -- web/static/corpus-takeaway.js scripts/test_p2_brainstorm_copy_format.mjs
```

Expected: all commands exit 0.
