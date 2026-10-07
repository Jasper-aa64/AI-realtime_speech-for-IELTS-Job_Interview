# Unified rounded brain branding

## Outcome
Finish the user's interrupted logo work. Use the new right-corner pink rounded-square brain body as the identity across AI assistant controls/header, top-left brand and switcher, browser favicon/touch icon, and actual Qt desktop bundle/window icon. Keep dark/light appearance and layout stable. The brain (eyes/folds) fills each logo; no arms/legs/embedded bulb competing for space. Top-left bulb is an absolute decorative overlay, hidden at rest, pops and floats on hover/focus or switcher-open, consumes no layout space; reduced motion shows a static bulb and no blinking/bobbing.

## Inputs and ownership
Existing commit07ccf66 defines the corner brain body (pink #f6bcca, outline #c46d87, folds #b15775, eyes #3a2530). Uncommitted index.html has three brand-logo+brand-bulb wrappers; finish those changes in scope. Untracked studio-brain.svg is an interrupted earlier body-with-arms/legs asset; replace with canonical rounded body per current user request. Preserve all unrelated dirty docs/reports handoff and backend_django/db.sqlite3 edits. Branch ui-polish, local commits only/no push.

## Contract
Canonical SVG web/static/assets/brand/studio-brain.svg has rounded square20x20 viewBox, fills pink body with dark outline, centered fold and four short fold marks, two pixel eyes with preserved centers and enlarged squares (user follow-up: 22% wider, 2.44 instead of 2 units on the20x20 viewBox). Bulb belongs to HTML decoration, never this canonical icon. All web brand/assistant slots reference the canonical asset (no independent drifting drawing). Generated favicon ICO, touch PNG, and desktop ICNS/PNG derive from that SVG reproducibly via trusted installed SVG renderer. Preserve eye blinking if practical through the shared SVG itself, disable via prefers-reduced-motion; raster exports static open eyes.

Web implementer owns web/static/index.html/styles.css/interview-assistant.js (other assistant control references if present), specs frontend brand guideline. Icon implementer owns canonicalSVG, conversion script and exported assets, desktop CMake/Info.plist/main/qrc resource/readme. Coordinate canonical name/version20261007-rounded-brain-2. No server restart needed for existing assets path; do not restart stacks/tunnel for styling. Desktop build only; no abrupt killing existing app or login teardown changes.

## Acceptance
Visually inspect web/desktop at normal and narrow sidebar, light/dark, resting/hover/open/reduced-motion if CUA available. Bulb extends beyond logo without clipping or shifting text/control; mark enlarged and square; icon-only controls square. All intended assistant+branding slots share drawing. SVG valid, generated PNG/ICO/ICNS sizes/plist bundle resource correct, Qt build/tests pass. Run existing relevant front-end suite. No new tests mirroring reversible CSS; only update meaningful existing assertions that encode superseded asset references. No image-generation tool for existing repo-native SVG work.

## Verification completed 2026-10-07
- Final user adjustment: eyes are 2.44 by 2.44 (22% above original 2 by 2), preserving centers. All raster exports regenerated and independently matched to the source.
- Frontend existing suite: 116/116 passed; JS syntax and diff formatting passed. Qt desktop builds; 4/4 CTests passed after final raster update. ICNS layers, PNG/ICO dimensions and built bundle icon/plist verified.
- CUA actual window: resting logo and assistant navigation/corner/header/welcome match; open switcher bulb extends without clipping or shifting the wordmark. Sidebar checked at about 180 and 150 CSS pixels, restored to prior width. Screenshots saved in the chat outputs directory.
- Reduced-motion rules reviewed statically. Dark appearance was not exercised in this run: the app window closed during the appearance inspection. No server or worker restarted.
- Unrelated database, existing handoff report and prior workspace journal changes are excluded.

## Follow-up correction from user
The top-left brand is a special exception: use the previous pixel brain mascot shape, not the rounded square body. Preserve the enlarged brain-first footprint and independent floating bulb (no bulb in resting image). Apply this special mascot consistently to regular brand, desktop switcher trigger and switcher card head. Assistant/nav/browser/app icon keep rounded brain with 22% eyes. Remove the small brain from the top-left of the corner assistant popup header; preserve title and centered welcome brain. Also remove the small icon before AI 助手 above the full-page search/chat list, preserving text title and centered welcome icon. The mascot must keep the original raised right arm paired with the separate floating bulb; do not lower it. Bump CSS/assistant script caches.

Final animation preference: after the bulb pops out, it remains fixed next to the raised hand. Remove the repeating vertical float/bob/rotation; keep pop-in and ray twinkle. Reduced motion stays static.

Final placement preference: lower the bulb by 2 CSS pixels from the original paired-hand alignment, consistently in all top-left brand slots.

## Follow-up verification
- Original mascot body, eyes, folds, feet and raised right arm match studio-logo.svg exactly; all three global top-left slots use the new tightly cropped mascot asset.
- Both full-page chat-list and corner-popup title icons removed, centered welcome image preserved. Bulb animation now has one 320ms pop and ray twinkle, no recurring translation/rotation; shared position lowered 2 CSS pixels.
- Existing 116 frontend tests passed after initial follow-up; later changes are SVG pose, icon removal and CSS animation/offset only. Final JS syntax, SVG parsing and diff checks pass; reviewer found no defects.
- Actual native screenshot confirms the old pixel mascot and raised hand paired with bulb. App interaction was interrupted by ongoing user control; final animation/offset verified from CSS rather than forcing more actions.

## Final refinement: reuse existing idea animation
User asks to lower bulb again and reuse an existing in-interface bulb animation. Lower by another 2 CSS pixels (total +4px from original geometric alignment). Reuse actual existing follow-up fuBulbPop and fuBulbRay keyframes for brand hover/focus/open, rather than duplicate brandBulbPop/brandBulbTwinkle. Existing follow-up keyframes end in fade-out for fly-away: parameterize only their ending opacity/transform via CSS variables with unchanged defaults, and let brand override end state to visible scale(1). Use original 650ms ease-out bounce/ray reveal; final brand position remains fixed with no repetitive bob. Remove obsolete brand-specific keyframes. Other original follow-up behavior stays unchanged. Reduced motion remains static. Update cache version and convention.

### Reused animation validation
Existing 116 frontend tests pass after the shared keyframe change. Reviewer confirms unchanged follow-up default frames and brand-only visible ending overrides; syntax/diff checks pass. Native CUA refreshed the app, opened the workspace switcher, and confirmed the bulb sits at its lower raised-hand position with no bobbing after the pop. Saved reused-bulb-animation.png in chat outputs and closed the menu.

## Placement adjustment
Move the shared brand bulb down another 2 CSS pixels (total +6px from original alignment) and left by 2 CSS pixels (add +2px to right). Apply consistently to all three top-left positions. Preserve reused animation, no other behavior changes. Refresh stylesheet cache.
