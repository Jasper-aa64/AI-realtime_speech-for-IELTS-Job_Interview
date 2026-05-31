# Howler.js Playback Research

## Sources

- Search results:
  - https://howlerjs.com/
  - https://github.com/goldfire/howler.js
- Context7 docs for `/goldfire/howler.js`.

## Relevant API Facts

`Howl` supports:

- `src: [...]`
- `html5: true | false`
- `preload: true | false | "metadata"`
- `format: [...]`
- `onload`
- `onloaderror`
- `onplay`
- `onplayerror`
- `onend`
- `onpause`
- `onstop`
- `unload()`

Example shape from docs:

```js
const sound = new Howl({
  src: ["sound.mp3"],
  html5: true,
  preload: true,
  onload() {},
  onplay() {},
  onend() {},
  onloaderror(id, error) {},
  onplayerror(id, error) {},
});
```

Docs also show a mobile/browser play-error pattern:

```js
sound.once("unlock", function() {
  sound.play();
});
```

## Decision

Use `howler.js` as the P1 examiner TTS playback engine. Keep the IELTS state
machine outside the audio engine. The wrapper should expose a small promise or
callback contract so P1 code only handles:

- loading,
- playback started,
- playback ended,
- playback failed,
- stop/unload.

## Integration Notes

- Prefer `html5: true` for examiner TTS because the backend serves stable audio
  files and this avoids relying on our own WebAudio decode path.
- Keep stable URL conversion for `/api/tts-audio/examiner/...`.
- One Howl per active turn is enough; unload old sounds on turn changes.
- Do not keep old hidden `<audio>` and Howl as two active engines.
