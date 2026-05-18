# Fix Language Takeaway Proxy and Save Flow

## Goal

Make the new Language Takeaway feature usable from the current browser runtime, including the old `web/ielts_server.py` static/proxy server path. The user currently sees `404 Not Found` when loading the takeaway list and when saving from the selection popup.

## What I Already Know

- Django already registers:
  - `GET/POST /api/language-takeaways`
  - `POST /api/language-takeaways/translate`
  - `GET/POST /api/p1-corpus`
  - `GET/POST /api/p2-corpus`
- The frontend calls those exact paths.
- The old web server proxy only forwards accounts, selected writing/AI task paths, and optional speaking runtime paths.
- Therefore pages served through the old server can return `404 Unknown API endpoint` before Django sees the request.
- If `CAIYUN_TOKEN` is not configured, translation should remain editable instead of pretending a translation exists.
- The referenced Pot App Caiyun plugin uses the public Caiyun interpreter protocol with a bundled compatibility token. We may use the protocol shape but must not copy GPL code.

## Requirements

- Old server must proxy corpus and language takeaway endpoints to Django when the user has a Django session cookie.
- Proxy must preserve cookies, JSON body, and `X-CSRFToken`.
- Language Takeaway list loading must work instead of showing `Request failed: 404 Not Found`.
- Selection popup must allow manual save even when translation provider token is missing or unavailable.
- Do not add browser-side secrets.
- Do not fake translation when Caiyun is unavailable.
- Translation should prefer the Caiyun compatibility protocol without user configuration, then fall back to local offline phrase/word lookup.

## Acceptance Criteria

- [x] Old server proxies `GET /api/language-takeaways` to Django with a `sessionid` cookie.
- [x] Old server proxies `POST /api/language-takeaways` to Django with body, cookie, and CSRF token.
- [x] Old server proxies `POST /api/language-takeaways/translate` to Django.
- [x] Old server proxies `GET/POST /api/p1-corpus` and `GET/POST /api/p2-corpus`.
- [x] Frontend shows a clear editable state for missing translation provider token.
- [x] Translation uses Caiyun compatibility protocol without local token configuration.
- [x] Translation falls back to local offline dictionary when Caiyun is unavailable.
- [x] 生词本 is a separate corpus page, not an inline panel on the corpus home.
- [x] 生词本 renders saved words/phrases as fixed-size two-column cards.
- [x] Hidden Chinese mode preserves card size and reveals Chinese after click.
- [x] Clicking a card plays the English phrase with local browser TTS and reveals the Chinese text.
- [x] Left navigation places 语料库 and 生词本 together in the lower options area, with 生词本 directly under 语料库.
- [x] 生词本 cards show only English and Chinese text, with smaller English type and compact card sizing.
- [x] Existing Django Language Takeaway save/list tests still pass.
- [x] `node --check web/static/app.js` passes.
- [x] `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py` passes.

## Out of Scope

- Configuring real `CAIYUN_TOKEN`.
- Adding a second translation provider.
- Redesigning the corpus UI.
- Committing or pushing unrelated existing dirty files.

## Technical Notes

- Primary files: `web/ielts_server.py`, `web/static/app.js`, `tests/test_ielts_web_server.py`.
- Related Django implementation already exists under `backend_django/apps/speaking/`.
