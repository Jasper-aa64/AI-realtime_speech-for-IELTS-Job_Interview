# Brainstorm card interaction without green wash

## Goal
User points to the P2 corpus home card titled 串题灵感 Brainstorm (62/64) with copy 按题干快速记一句灵感… and wants no green layer when selected/hovered/focused. Preserve the resting appearance, pixel flow particles, mascot animation, count/copy and click-to-open dialog.

## Scope / approach
Inspect .p2-brainstorm-entry-card / .p2-brainstorm-open-card cascade in styles.css. Known sources: light hover/focus gradient increases category color intensity at8676; dark hover/focus sets rgba(20,83,75,.28) at21933, grouped with unrelated dialog rows. Remove card-only green state fills while retaining each theme's existing resting background. Do not change dialog-row focus/hover, category cards or global button styles. Keyboard focus must remain discernible with a small appropriate outline if needed, not a whole-card wash. Bump stylesheet cache in index.html. Reversible CSS only; no cosmetic tests.

## Acceptance
- Brainstorm card background stays consistent from resting to pointer hover and keyboard focus in light/dark themes.
- Pixel/brain effects and dialog behavior unchanged.
- Correct narrow selectors, no broad override. Diff formatting and review pass; CUA visual check if app window can be operated.

## Constraints
Branch ui-polish, local commit authorized, no push. Preserve unrelated backend_django/db.sqlite3, existing handoff report and workspace journal changes. No server or worker restart for CSS. No clarification needed; user states preference explicitly.

## Verification
Independent review passed: scoped selectors win over the old hover/focus fills in both themes; reused interview CTA and dialog rows are unchanged. Native app was refreshed and the resting card inspected. Diff formatting passed. No new reusable spec convention from this narrow cosmetic adjustment.
