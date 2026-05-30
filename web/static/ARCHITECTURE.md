# Frontend Runtime Architecture

`web/static/` is the production browser runtime for the IELTS app. The current
SPA is intentionally still served as simple static assets by Django.

## Baseline

- `index.html` owns stable DOM anchors.
- `app.js` owns the current single-page application behavior.
- `styles.css` owns the current visual system.
- Django serves these assets and all `/api/*` calls.

The baseline user flows must remain stable while the large files are split.
Do not replace the SPA with a framework as part of routine refactors.

## Extraction Boundaries

Future JavaScript extraction should happen in this order:

1. `api-client` boundary: CSRF, `api()`, auth recovery, and request errors.
2. `writing` boundary: prompt rendering, report rendering, writing task
   polling/result notification, and prompt bank UI.
3. `speaking` boundary: attempt lifecycle, audio recording, turn completion,
   score polling, and report rendering.
4. `corpus-takeaway` boundary: P1/P2 corpus windows, Takeaway popover, and
   translation/save flows.
5. `shared-ui` boundary: modal, confirm, markdown, navigation, and report rail
   helpers.

Each extraction must keep the global behavior compatible until the whole app is
module-loaded. Prefer small `window.IELTS...` namespaces or non-module scripts
first; do not introduce a bundler until the current static deployment is
explicitly changed.

## Production Rule

No frontend module should call the retired `web/ielts_server.py`. All network
traffic goes through the Django `/api/*` surface.
