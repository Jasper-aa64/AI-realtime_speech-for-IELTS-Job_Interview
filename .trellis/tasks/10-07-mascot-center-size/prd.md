# Slightly smaller centered top-left mascot pair

## Goal
User wants the current old pixel brain at top-left to shrink toward its center a little, and the paired bulb to shrink as well. Preserve the last down/left placement adjustment and current popup animation. User also asks to see each change without manually pressing Cmd+R; root will refresh the running desktop window after applying changes.

## Scope / approach
CSS-only top-left .brand-logo pair, both resting switch trigger and open switch header / static fallback. Recommended subtle scale: 92% of current size, around the logo box center. Keep layout footprint and wordmark position stable; scale both brain and bulb together so their pairing stays intact. Prefer wrapper scale without touching child's animation transform. Preserve old raised-hand SVG, existing 650ms bulb/rays animation, fixed final bulb, reduced-motion behavior and rounded-brain icons elsewhere. Bump stylesheet cache. Root handles UI refresh/verification, no server/worker restart.

## Acceptance
- Brain and bulb are slightly smaller, centered within same reserved logo area.
- Raised-hand pairing/last placement and animation remain coherent in resting and open switcher states.
- AI rounded logos / app assets / wordmark / navigation layout unchanged.
- Diff check and independent cascade review pass. Root refreshes desktop and captures visual result where operable.

## Constraints
Local ui-polish commit authorized; no push. Preserve unrelated DB/report/workspace changes. No new cosmetic tests or speculative auto-reload mechanism; refresh desktop at completion as requested.

## Verification
Independent review and diff formatting pass. Wrapper scale preserves layout and child animation in normal/reduced motion; rounded assistant and app icons untouched. Desktop Cmd+R executed and boot state confirmed reload. Resting visual captured, switcher open/close confirmed by AX; no new reusable spec convention.
