(function () {
  const unavailable = Object.freeze({ protocol_version: 1, desktop: false, mock_interview: false, native_audio: false });
  const ready = new Promise((resolve) => {
    if (window.top !== window || !window.qt?.webChannelTransport || typeof window.QWebChannel !== "function") {
      resolve(unavailable);
      return;
    }
    const timeout = window.setTimeout(() => resolve(unavailable), 2500);
    try {
      new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
        const bridge = channel.objects?.studioNative;
        if (typeof bridge?.capabilities !== "function") {
          window.clearTimeout(timeout);
          resolve(unavailable);
          return;
        }
        bridge.capabilities((value) => {
          window.clearTimeout(timeout);
          if (value?.protocol_version !== 1 || value.desktop !== true || value.mock_interview !== true) {
            resolve(unavailable);
            return;
          }
          resolve(Object.freeze({ protocol_version: 1, desktop: true, mock_interview: true, native_audio: value.native_audio === true }));
        });
      });
    } catch (_error) {
      window.clearTimeout(timeout);
      resolve(unavailable);
    }
  });
  window.IELTSNativeBridge = Object.freeze({ ready });
})();
