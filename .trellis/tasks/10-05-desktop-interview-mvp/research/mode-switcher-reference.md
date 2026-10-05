# Mode switcher reference (2026-10-05)

Inspected detail.design before implementation through Firecrawl:
- https://detail.design/ (catalog and motion references)
- https://detail.design/detail/smart-corner-morph-animation (Motion, August 28 2026)
- https://detail.design/detail/avoid-browser-default-back-behavior

The motion reference exposes a video player and a technical breakdown link. Browser access from this worker was unavailable, and the text scrape does not expose playable frames. **Frame timing and corner interpolation were not verified; no frame-by-frame claim is made.**

Implementation decision: use a restrained top-left anchored menu; short opacity/translation reveal from the trigger, stable item bounds, keyboard focus and immediate Escape/outside close. Honor prefers-reduced-motion by removing reveal animation. Avoid inventing a measured duration based on the reference; 140 ms is our chosen UI duration. Global settings/account remain in the existing shell. Root will inspect the actual built desktop UI.

Qt bridge reference: https://doc.qt.io/qt-6/qtwebchannel-javascript.html and installed Qt 6.11.2 framework headers (QWebEnginePage::setWebChannel, QWebChannel::registerObject). Context7 lookup failed with an expired OAuth token. The bridge uses the installed qwebchannel.js resource injected at document creation rather than relying on remote pages fetching a local qrc URL; native calls are asynchronous and initialization is single per transport.


## Measured in the browser (Claude, 2026-10-05 evening)

Opened https://detail.design/ in the in-app browser, clicked the top-left mark and read the shipped bundle (`3l5tnseyg2g7h.js`):

- Container: `motion.div layout="size"`, `transition: { type: "spring", stiffness: 300, damping: 30, bounce 0.1 for idle↔expanded }`, `style.borderRadius = 24`, classes `relative grid w-fit overflow-hidden bg-black border-2 border-white/10`. Open card measured 324×319.
- Content: two children stacked in `grid-area 1/1`, keyed by state under `AnimatePresence`; enter `opacity 0→1, filter blur(4px)→blur(0)` 0.2 s, exit `opacity→0, blur(4px)` 0.1 s. The trigger mark also flies as a shared element (`x/y/scale` from→to).
- Rendered frames: a small dark box grows from the corner while the mark stays put; text appears once there is room (no reflow, clipped by the container).

Our implementation: spring ζ≈0.87 sampled into CSS `linear()` (500 ms open, 380 ms close), opaque background throughout (sidebar `--nav` → darker card), head row repeats the brand at the trigger's exact position so it reads as the same element, body cross-fades with blur. Programmatic focus uses `preventScroll` — otherwise Chromium scrolls the clipped card and the head disappears mid-animation. Reduced motion: opacity only, 120 ms.
