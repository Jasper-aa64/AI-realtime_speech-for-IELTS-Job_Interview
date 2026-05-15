# Optimize writing reports list hydration

## Goal

Eliminate the N+1 detail fetch fan-out in the writing reports page. The `/api/writing/reports` API already returns compact report items with all metadata needed for the left list/tabs, but the frontend currently fetches full detail for every item immediately. This task makes the list render from compact data and defers detail fetch to selection time.

## What I Already Know

* `GET /api/writing/reports` returns `{"items": [...], "count": N}` with compact fields.
* Compact item includes: `id`, `practice_date`, `display_time`, `task_type`, `task_label`, `title`, `word_count`, `status`, `overall_band`, and `ai_task` summary (id, task_type, status, related_type, related_id).
* Current `renderWritingReports()` (line 1357) does:
  ```js
  const entries = await Promise.all(items.map((item) => api(`/api/writing/entries/${item.id}`)));
  ```
  This fetches ALL detail for ALL items on initial load.
* `writingReportTabHtml()` only uses fields available in compact items: `task_type`, `title`, `practice_date`/`display_time`, `word_count`, `score.overall_band` (via `overall_band` on item), and `ai_task.status`.
* `writingReportDetailHtml()` needs full detail: answer, prompt, feedback, grammar corrections, and `writing_profile`.
* Polling `startWritingScorePolling(entry.id, ...)` only needs `entry.id` and `entry.ai_task` which compact items have.

## Assumptions (temporary)

* The compact payload's `overall_band` mirrors `score.overall_band` for scored entries.
* `writing_profile` is only needed in detail view and only fetched on selection.
* Users typically view 1–2 reports per visit, not all N items.

## Technical Findings (from code inspection)

**Polling flow** (lines 1638-1672):
* `startWritingScorePolling(entryId)` fetches `/api/writing/entries/${entryId}` every 2.5s
* On update, `renderVisibleWritingReport(entry)` updates `state.writing.reportEntries[index]` with full entry
* This already handles list + detail sync during polling

**Tab rendering** (lines 1388-1404):
* Uses: `task_type`, `title`, `practice_date`/`display_time`, `word_count`, `overall_band`, `ai_task.status`
* ALL available in compact payload

**Detail rendering** (lines 1407+):
* Needs: full answer, prompt, feedback, grammar corrections, `writing_profile`
* NOT in compact payload — must fetch detail

## Decision (ADR-lite)

**Context**: Writing reports page currently fetches N detail entries on initial load. `/api/writing/reports` now provides compact items with all list metadata, offering an optimization opportunity.

**Decision**: Store compact items in `reportEntries`. Fetch detail only on selection. No session cache.

**Consequences**:
- Eliminates N+1 fetch on page load.
- Simple implementation: no cache invalidation logic.
- Polling naturally provides fresh detail during active scoring.
- Future: if users frequently re-select same report and perceive slowness, add cache separately.

## Requirements

* Store compact items (from `/api/writing/reports`) in `state.writing.reportEntries`.
* Render left list/tabs directly from compact items — no detail fetch for list.
* Track selected report id in `state.writing.activeReportId`.
* Fetch full detail (`GET /api/writing/entries/{entry_id}`) only when user selects a report.
* Store fetched detail in a separate variable (e.g., `state.writing.activeReportDetail`) for rendering.
* Continue polling for `pending`/`running` ai_task on the selected report.
* When polling fetches updated entry, update both `activeReportDetail` and the corresponding compact item in `reportEntries` (merge `overall_band`, `status`, `ai_task`).
* No session cache for detail — re-select always fetches fresh.

## Acceptance Criteria

* [ ] Initial `loadWritingReports()` makes exactly 1 API call (`/api/writing/reports`).
* [ ] Left list renders correctly from compact items (task type, title, date, word count, band/status).
* [ ] Detail fetch occurs only on user selection, not on initial load.
* [ ] Selecting a report fetches `/api/writing/entries/{id}` and renders detail.
* [ ] Polling continues to work for pending/running tasks on selected report.
* [ ] Tab updates (band/status) when polling receives score completion.
* [ ] Re-selecting same report fetches fresh detail (no cache).
* [ ] Network tab shows N requests on page load, not N+1.

## Definition of Done

* Frontend syntax check passes.
* Django tests remain green (no backend changes).
* Manual smoke test: load reports page, verify network requests.
* No speaking, C++, or UI redesign changes.

## Out of Scope (explicit)

* No backend API changes.
* No pagination UI.
* No speaking reports migration.
* No Vue migration.

## Technical Approach

**State structure changes**:
```js
state.writing = {
  reportEntries: [],      // compact items from /api/writing/reports
  activeReportId: null,   // selected report id
  activeReportDetail: null, // full detail of selected report (or null)
  // ... existing fields
};
```

**Function changes**:
1. `loadWritingReports()`: Store compact items, select first, fetch its detail.
2. `renderWritingReports(items)`: Store items, render list, fetch detail for first/selected item.
3. `renderWritingReportList(entries)`: Accept compact items, use compact fields for tab HTML.
4. `writingReportTabHtml(item)`: Adapt to compact item shape (use `overall_band` directly, not `score.overall_band`).
5. Tab click handler: Fetch detail for selected id, store in `activeReportDetail`, render detail.
6. `renderVisibleWritingReport(entry)`: Update `activeReportDetail` + merge into `reportEntries[index]`.
7. `startWritingScorePolling()`: Already fetches detail; wire to update `activeReportDetail`.

**Compact item → tab mapping**:
- `item.task_type` → T1/T2 label
- `item.title` → tab title
- `item.display_time` or `item.practice_date` → time display
- `item.word_count` → word count
- `item.overall_band` → band display (or "未评分"/"评分中")
- `item.status` → status badge
- `item.ai_task.status` → polling indicator

## Technical Notes

* Key file: `web/static/app.js`
* Functions to modify: `loadWritingReports()`, `renderWritingReports()`, `renderWritingReportList()`, `writingReportTabHtml()`, `renderVisibleWritingReport()`.
* No backend changes required.
* Tests: Django tests remain green; manual smoke test for network requests.
