# Research: ready-state-diagnosis

- **Query**: Research the examiner HTMLAudio playback readiness path in `web/static/app.js`. Focus on whether dynamic TTS starts at a lower readyState than fixed audio, whether `/api/tts-audio/examiner` URLs are used directly, and whether any existing blob preload/stable-url helpers are present.
- **Scope**: internal
- **Date**: 2026-05-31

## Findings

### Files Found

| File Path | Description |
|---|---|
| `web/static/app.js` | Examiner audio playback, readiness wait, URL helpers, and TTS refresh path. |
| `.trellis/spec/backend/quality-guidelines.md` | Spec note requiring a bounded frontend wait for refreshed examiner TTS. |
| `.trellis/spec/frontend/quality-guidelines.md` | Voice-first playback requirement for P1/P2/P3 examiner audio. |

### Code Patterns

`web/static/app.js` uses one shared `HTMLAudioElement` (`$("examinerAudio")`) for both fixed and dynamic examiner playback. The branch that differentiates fixed audio is `const isFixedAudio = FIXED_EXAMINER_AUDIO_URLS.has(tts.audio_url);` in `playExaminerTurn()` at `web/static/app.js:2334`. The fixed list contains three direct `/api/tts-audio/examiner/...mp3` paths at `web/static/app.js:218-222`.

Dynamic and fixed audio both resolve through `resolveExaminerAudioPlaybackUrl(tts.audio_url)` before assignment. That helper currently returns the original URL unchanged and traces `media-audio:direct-url`:

```js
async function resolveExaminerAudioPlaybackUrl(url) {
  if (!url) return "";
  traceExaminerAudio("media-audio:direct-url", { url });
  return url;
}
```

Source: `web/static/app.js:1945-1949`.

The selected URL is then passed directly into `prepareExaminerAudioElement(audio, playbackUrl, tts.audio_url)`, which sets `audio.preload = "auto"`, writes `audio.src = playbackUrl`, and calls `audio.load()` when the src changes. Source: `web/static/app.js:1931-1943`, `web/static/app.js:2347-2358`.

The readiness threshold is lower for non-fixed audio. `waitForAudioReady()` defaults to `targetReadyState` 3, and `playExaminerTurn()` calls it with:

```js
targetReadyState: isFixedAudio ? 4 : 3,
timeoutMs: isFixedAudio ? FIXED_AUDIO_READY_TIMEOUT_MS : AUDIO_READY_TIMEOUT_MS,
```

Source: `web/static/app.js:2081-2130`, `web/static/app.js:2360-2364`.

`waitForAudioReady()` considers the audio ready once `audio.readyState >= targetReadyState`, listening to `loadeddata`, `canplay`, and `canplaythrough`, with timeout/error fallback. Source: `web/static/app.js:2102-2129`.

A stable-url helper exists but is not used in the observed playback path:

```js
function stableExaminerAudioUrl(url) {
  if (!url || !url.includes("/api/tts-audio/examiner/")) return url;
  try {
    const parsed = new URL(url, window.location.origin);
    parsed.searchParams.set("stable", "1");
    return parsed.pathname + parsed.search;
  } catch {
    return url.includes("?") ? `${url}&stable=1` : `${url}?stable=1`;
  }
}
```

Source: `web/static/app.js:1951-1960`. Search within `app.js` found only the definition, with no call sites.

Blob-preload state also exists but no blob creation or population logic was found in `app.js`. `state.examinerAudioBlobUrls` is initialized at `web/static/app.js:92`, and `clearExaminerAudioPreloads()` revokes `item.playbackUrl` object URLs and clears the map at `web/static/app.js:1962-1968`. Search found no `createObjectURL(` call and no `.set(...)` call on `examinerAudioBlobUrls` in this file.

Pending dynamic TTS can be refreshed via `/api/attempts/{attemptId}/turns/{turn.id}/examiner-tts` before playback. `refreshPendingExaminerTts()` updates `turn.examiner_tts` and returns once `audio_url` is present or the bounded wait expires. Source: `web/static/app.js:2141-2189`.

### External References

None.

### Related Specs

- `.trellis/spec/backend/quality-guidelines.md` — `Generated follow-up turns must have a server TTS refresh path`, including: "The frontend may wait only a bounded short window for refreshed TTS, then continue safely." Source: `.trellis/spec/backend/quality-guidelines.md:92-101`.
- `.trellis/spec/frontend/quality-guidelines.md` — P1/P3 should auto-play examiner questions and P2 should play instruction audio. Source: `.trellis/spec/frontend/quality-guidelines.md:61-67`.

## Caveats / Not Found

- This note is limited to `web/static/app.js` and related specs; no other frontend module was searched for blob-preload helpers.
- No existing call site was found in `app.js` for `stableExaminerAudioUrl()`.
- No existing blob preload population path was found in `app.js`; only cleanup state and revocation logic are present there.
