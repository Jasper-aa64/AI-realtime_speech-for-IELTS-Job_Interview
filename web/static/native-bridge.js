(function () {
  const unavailable = Object.freeze({ protocol_version: 1, desktop: false, mock_interview: false, native_audio: false });
  // studioVoice (desktop realtime voice) resolves to null unless the shell reports native_audio.
  let resolveVoice = () => {};
  const voice = new Promise((resolve) => { resolveVoice = resolve; });
  const ready = new Promise((resolve) => {
    const finish = (value, voiceObject = null) => {
      resolveVoice(value.native_audio === true ? voiceObject : null);
      resolve(value);
    };
    if (window.top !== window || !window.qt?.webChannelTransport || typeof window.QWebChannel !== "function") {
      finish(unavailable);
      return;
    }
    const timeout = window.setTimeout(() => finish(unavailable), 2500);
    try {
      new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
        const bridge = channel.objects?.studioNative;
        if (typeof bridge?.capabilities !== "function") {
          window.clearTimeout(timeout);
          finish(unavailable);
          return;
        }
        bridge.capabilities((value) => {
          window.clearTimeout(timeout);
          if (value?.protocol_version !== 1 || value.desktop !== true || value.mock_interview !== true) {
            finish(unavailable);
            return;
          }
          const voiceObject = typeof channel.objects?.studioVoice?.startSession === "function" ? channel.objects.studioVoice : null;
          finish(Object.freeze({ protocol_version: 1, desktop: true, mock_interview: true, native_audio: value.native_audio === true && !!voiceObject }), voiceObject);
        });
      });
    } catch (_error) {
      window.clearTimeout(timeout);
      finish(unavailable);
    }
  });
  window.IELTSNativeBridge = Object.freeze({ ready, voice });
})();
