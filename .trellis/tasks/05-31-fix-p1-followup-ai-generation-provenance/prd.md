# Replace P1 Examiner TTS Playback With Howler.js

## Goal

Stabilize P1 examiner TTS playback by replacing the current hand-rolled
playback layer with a small, authoritative player built on `howler.js`.

The current implementation has been repeatedly patched and still produces
tearing/stutter after the first fixed question, plus follow-up states that can
skip audio and enter preparation. Stop adding playback-state patches. Reuse a
well-maintained browser audio library and keep IELTS business flow separate from
low-level audio playback mechanics.

## Problem

The current P1 playback layer in `web/static/app.js` has accumulated:

- hidden `<audio>` element playback state,
- object URL / stable URL fetch logic,
- playback transaction state,
- diagnostics samplers,
- late async continuation guards,
- direct calls into preparation fallback paths.

This makes the browser audio pipeline fragile. The project needs one playback
abstraction that owns loading, playing, stopping, unloading, and end/error
events. IELTS flow code should only react to `ready`, `play`, `end`, and
`error`.

Additional root-cause evidence from headset testing: report-page TTS playback
is stable, while in-flow examiner TTS tears on some Bluetooth headsets
(`OPPO Enco X3` severe, `soundcore Space Q45` mild, `ROSE OpenFun` OK). That
points to browser audio session scheduling rather than TTS content alone:
examiner playback must not overlap with active or still-tearing-down microphone,
browser dictation, realtime PCM, or WASM/AudioWorklet processing. Playback and
recording are mutually exclusive audio sessions.

Follow-up diagnosis on the user's machine showed `OPPO Enco X3` was both the
default output and the default input (`Bluetooth`, input sample rate 16000Hz).
Stopping the recording stack before playback was not enough because the next
recording still opened the Bluetooth headset microphone, and browser
`SpeechRecognition` can also reopen the system default mic without respecting a
chosen `MediaStream` device. The browser must prefer a non-Bluetooth input
device for recording and avoid browser dictation when Bluetooth inputs are
present.

## Reused Resource

Use `howler.js` as the browser audio playback engine.

Rationale:

- mature browser audio library,
- single `Howl` API,
- supports preload,
- supports `onload`, `onplay`, `onend`, `onloaderror`, `onplayerror`,
- supports explicit `html5` playback mode for browser-native streaming/large
  files,
- supports `unload()` cleanup.

This also strengthens Experiment 5: the project reuses `libfvad` for audio
analysis and `howler.js` for stable browser TTS playback.

## Scope

- Add `howler.js` to the frontend in the simplest maintainable way:
  - prefer a vendored static asset under `web/static/vendor/` or a Django-served
    static module, not a browser-side secret or external API key;
  - make the load path cache-busted through `index.html`.
- Replace P1 examiner TTS playback internals with an `ExaminerAudioPlayer`
  wrapper around `Howl`.
- Keep a single authoritative entrypoint, e.g. `playExaminerTurn(turn)`.
- Keep stable TTS URL handling:
  - examiner TTS URLs under `/api/tts-audio/examiner/...` must still resolve to
    `?stable=1`;
  - do not directly prefer VolcEngine raw MP3 for playback.
- Preserve current P1 business behavior:
  - fixed question playback,
  - dynamic follow-up playback,
  - no-audio fallback,
  - turn progression,
  - realtime ASR / browser dictation fallbacks.
- Before calling `Howl.play()`, release the learner recording stack:
  - stop browser dictation and dictation restart timers;
  - wait for any active WASM/AudioWorklet preprocessor stop promise;
  - stop realtime PCM upload / ASR socket if it is still open;
  - stop stale microphone `MediaStreamTrack`s;
  - wait a short drain interval so Bluetooth headsets can leave hands-free
    capture mode before examiner playback begins.
- Before recording, enumerate `audioinput` devices and prefer a built-in /
  internal / non-Bluetooth microphone for `getUserMedia`. If a baseline default
  capture opens a Bluetooth headset mic, stop it immediately and retry with the
  preferred non-Bluetooth device after labels become visible.
- Expose the selected capture device through diagnostics so the user can confirm
  that OPPO remains output only while MacBook/internal mic is used for input.
- Disable browser `SpeechRecognition` in Bluetooth compatibility mode because it
  cannot be constrained to the selected non-Bluetooth `MediaStream` and may
  reopen the default Bluetooth microphone.
- Remove or bypass old player plumbing that is now redundant:
  - no second parallel playback engine;
  - no WebAudio/HTMLAudio dual-path conflict;
  - no diagnostics sampler as a required runtime component.

## Non-goals

- Do not redesign the full P1/P2/P3 practice flow.
- Do not change scoring/report generation.
- Do not remove realtime ASR, WASM preprocessing, or browser dictation.
- Do not introduce API keys or remote secrets in frontend code.
- Do not push to remote.

## Required Playback Contract

For every examiner turn:

1. Resolve stable playback URL.
2. Load via `ExaminerAudioPlayer`.
3. Show "Listening..." only after playable audio starts.
4. On playback end, and only then, enter preparation.
5. On load/play failure, show a clear no-audio fallback and enter preparation
   without pretending the examiner is still speaking.
6. If a new turn starts, stop/unload the previous Howl and ignore late events.
7. Repeated calls for the same active turn must be idempotent.
8. Examiner audio must begin only after the learner recording stack has been
   released or the release timeout expires; recording restarts only after
   playback end / visible no-audio fallback.
9. Speaking recording should use non-Bluetooth input when possible, and
   `window.__ieltsSpeakingInputDevice` should show the selected capture source.

## Acceptance Criteria

- `web/static/app.js` no longer contains the old examiner playback tangle as the
  active path.
- P1 fixed first question and later fixed/dynamic questions use the same
  `ExaminerAudioPlayer` path.
- Follow-up with ready TTS plays before preparation starts.
- Follow-up with missing/failed TTS visibly falls back; it does not show fake
  listening.
- `node --check web/static/app.js` passes.
- Django `manage.py check` passes.
- Targeted speaking TTS/follow-up tests pass.
- Manual P1 smoke can be run at `http://127.0.0.1:8767/?view=p1`.
- Bluetooth headset smoke: P1 follow-up and later fixed questions should play
  with recording/realtime ASR stopped before playback. The user should test the
  problematic headset because automated fake microphones cannot reproduce the
  Bluetooth A2DP/HFP transition.
- With OPPO Enco X3 connected as output, `window.__ieltsSpeakingInputDevice`
  should report a non-Bluetooth capture label such as `MacBook Air Microphone`
  when available, and browser dictation should be skipped in compatibility mode.

## 2026-05-31 update: configurable speaking AI route

Speaking follow-up and speaking report generation should default to Aiapis / OpenAI-compatible ordinary chat calls with `gpt-5.4-mini`, not Codex CLI agent calls.

Runtime switches:

- `SPEAKING_AI_CALL_MODE`: global speaking AI route. Supported values: `chain`, `http`, `codex`, `fallback`.
- `SPEAKING_FOLLOWUP_AI_CALL_MODE`: route override for P1/P3 follow-up generation.
- `SPEAKING_REPORT_AI_CALL_MODE`: route override for speaking scoring/report/turn feedback generation.
- `SPEAKING_AI_MODEL`: global speaking HTTP model override.
- `SPEAKING_FOLLOWUP_AI_MODEL`: follow-up HTTP model override.
- `SPEAKING_REPORT_AI_MODEL`: report HTTP model override.

Default route is `chain`: HTTP chat first, Codex fallback second. Default speaking HTTP model is `gpt-5.4-mini`; it intentionally does not inherit `AI_HTTP_MODEL` so old global defaults cannot silently move speaking back to a slower model. HTTP calls still use `AI_HTTP_BASE_URL` and `AI_HTTP_API_KEY` for the OpenAI-compatible endpoint.
