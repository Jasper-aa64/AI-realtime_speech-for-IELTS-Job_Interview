# State Management

> How state is managed in this project.

---

## Overview

<!--
Document your project's state management conventions here.

Questions to answer:
- What state management solution do you use?
- How is local vs global state decided?
- How do you handle server state?
- What are the patterns for derived state?
-->

(To be filled by the team)

---

## State Categories

<!-- Local state, global state, server state, URL state -->

(To be filled by the team)

---

## When to Use Global State

<!-- Criteria for promoting state to global -->

(To be filled by the team)

---

## Server State

<!-- How server data is cached and synchronized -->

(To be filled by the team)

---

## Common Mistakes

### Appearance Preference Must Stay Separate from Effective Darkness

**Scope:** Shared web/Qt page appearance in `web/static/appearance.js`.

**Signatures:** `bootstrapAppearance()` runs in the document head before styles;
`createAppearanceControls({ state }).applyAppearanceMode(mode, { skipPersist })`
updates the runtime selection.

**Contract:** `state.appearanceMode` is `light`, `dark`, or `system`;
`state.darkMode` is the effective boolean driving `theme-dark` on html/body.
Persist the chosen mode in `ielts-appearance-mode`. A valid new preference wins
over legacy `ielts-dark-mode` (`1` = manual dark, `0` = manual light).
Explicit manual changes also update the legacy key; system changes never do.
Use the same resolver for first paint and runtime. Update cache-busters when
changing appearance, app bindings, or stylesheet assets.

**Validation / errors:** Invalid/missing new mode falls back to valid legacy
manual choice, then system. Denied storage follows system and allows session-only
changes. Missing `matchMedia` resolves system to light. Only system mode reacts
to `(prefers-color-scheme: dark)` changes; events must not write storage.

**Cases:** Good: a saved system choice follows OS changes after reload even when
legacy storage says dark. Base: fresh user follows OS. Bad: OS dark writes `1`
and accidentally turns system mode into a manual preference.

**Tests:** `tests/appearance-mode.test.js` covers first-paint/runtime agreement,
legacy/new precedence, invalid data, manual/system transitions, persistence,
storage denial, and media-query compatibility. Keep boot overlay checks green.

**Wrong vs correct:**

```js
// Wrong: treats an OS event as a persisted manual selection.
applyDarkMode(systemQuery.matches);

// Correct: refresh effective darkness only for system mode.
if (state.appearanceMode === "system") {
  applyAppearanceMode("system", { skipPersist: true });
}
```

<!-- State management mistakes your team has made -->

### Takeaway Daily Recall Uses 4 AM Review Days

Takeaway and Writing Bank recall are localStorage-backed SRS queues. Their
"today" boundary is 04:00, matching the spelling drill. New or newly-discovered
entries must be due on the current review day, not tomorrow; otherwise the
sidebar daily reminder can disappear immediately after saving material.

If the current day's local batch was previously marked completed with zero
items, adding or first discovering a due entry must reopen today's batch and
include that entry. Do not leave `__daily_batch.completedDay === today` blocking
new due items.

Wrong:

```js
records[id] = { due: nextReviewDayKey(), reps: 0 };
```

Correct:

```js
records[id] = { due: todayKey(), reps: 0 };
markTakeawayEntryDueToday("writing", saved.entry_id);
```

### Speaking Follow-Up State Must Respect Empty Answers

When a P1 work/study identity question (`Do you work or do you study?`) completes
with an empty transcript, the UI must not show "正在生成追问..." and must not start
follow-up streaming. Use the backend `follow_up_skipped` response to show a clear
message such as `没有检测到回答，已跳过追问。`, then move to the next available turn
or scoring state.

Wrong:

```js
setRecordButton("processing", "Saving", "正在生成追问...");
streamFollowUpForCompletedTurn(...);
```

### Direct P2 Practice Uses URL-Owned Cue State

When a corpus surface opens a specific P2 question in a new tab, pass the cue
through `?view=p2&p2_cue_id=<cue>&autostart=1`. `requestedRouteState()` maps
those fields into `state.p2Corpus.pinnedCueId`, then the normal `startPractice()`
flow consumes the cue. Remove `autostart` before starting so refresh cannot
submit another attempt.

Do not rely on parent-window memory, `window.opener`, or `sessionStorage` for
the selected cue. The new tab must be independently reloadable and must keep
using the existing authenticated practice path.

Correct:

```js
if (completePayload.follow_up_skipped) {
  text("recordStatus", completePayload.follow_up_skipped.message);
} else if (shouldStreamFollowUpTurn(completePayload.next_turn)) {
  streamFollowUpForCompletedTurn(...);
}
```
