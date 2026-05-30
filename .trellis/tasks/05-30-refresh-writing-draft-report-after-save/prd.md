# Refresh writing draft report after save

## Goal

When a saved writing draft is updated from the Daily Writing page, the Writing Reports page must show the latest saved content, word count, timestamp, and edit payload. The user should not see a stale draft in the report detail, and clicking `继续编辑` must reopen the latest saved answer.

## What I Already Know

- `saveWritingEntry()` saves via `POST /api/writing/entries` and updates `state.writing.entry`.
- Writing Reports keeps separate state:
  - `state.writing.reportEntries`
  - `state.writing.reportDetailCache`
  - `state.writing.activeReportDetail`
- `fetchWritingReportDetail()` prefers `reportDetailCache` and can return stale data.
- `editWritingReportEntry()` prefers cached detail when available.
- Therefore saving a draft needs to update or invalidate the matching report cache/list item.

## Requirements

- After saving an existing unscored writing entry, the matching Writing Reports item reflects the new word count and updated detail.
- If the saved entry is currently visible in Writing Reports, the visible detail re-renders immediately.
- If the user later opens Writing Reports, the active saved draft uses the latest cache/detail.
- Clicking `继续编辑` on a saved draft opens the latest saved answer, not the previous version.
- Scored report revision behavior remains unchanged.

## Acceptance Criteria

- [ ] `saveWritingEntry()` updates or invalidates `reportDetailCache` for the saved entry.
- [ ] `saveWritingEntry()` updates matching compact `reportEntries` metadata when possible.
- [ ] If the saved entry is the active visible report, the report detail is re-rendered.
- [ ] `继续编辑` reads the latest saved entry after save.
- [ ] `node --check web/static/app.js` passes.

## Out of Scope

- Redesigning Writing Reports.
- Changing writing report backend contracts.
- Changing scored-entry clone/revision behavior.

## Technical Notes

- Likely implementation points:
  - `saveWritingEntry()`
  - `renderVisibleWritingReport(entry)`
  - `fetchWritingReportDetail(entryId)` / cache invalidation
  - `writingReportEntryFromEditButton(button)`
