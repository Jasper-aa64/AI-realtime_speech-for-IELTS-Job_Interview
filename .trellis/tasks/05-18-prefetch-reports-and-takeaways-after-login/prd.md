# Prefetch Reports And Takeaways After Login

## Goal

Make the first visit to reports and language takeaway pages feel fast after login or page refresh by warming the existing client-side caches in the background.

## Problem

The previous cache reuse work improves repeat visits, but the first click into speaking reports, writing reports, or the takeaway book still waits for network requests. On the public tunnel this is noticeable because latency is higher than localhost.

## Scope

- Add frontend-only idle prefetch for:
  - speaking history list and first detail
  - writing reports list and first detail
  - language takeaway entries
- Trigger after authenticated account load, login, and registration.
- Keep prefetch non-blocking: no global busy state and no visible page jump.
- Reuse existing state caches.
- Reset prefetch state and caches on logout.

## Out Of Scope

- Backend endpoint changes.
- Database changes.
- Pagination redesign.
- Service worker/offline caching.
- Browser storage persistence.

## Acceptance Criteria

- [x] Logged-in page refresh schedules background prefetch after the initial view is shown.
- [x] Login and register success schedule the same prefetch.
- [x] Prefetch does not show the global busy bar.
- [x] Prefetch does not switch views or change sidebar/theme selection.
- [x] Speaking report first list/detail can render from warmed `historyItems`/`historyDetailCache`.
- [x] Writing report first list/detail can render from warmed `reportEntries`/`reportDetailCache`.
- [x] Takeaway book first render can use warmed `languageTakeaway.items`.
- [x] Logout clears warmed user-specific caches.
- [x] JS syntax check passes.

## Notes

This intentionally improves perceived first-click speed without changing backend contracts. Network latency for the first background request still exists, but it happens while the user is looking at the current page instead of after they click reports or the takeaway book.
