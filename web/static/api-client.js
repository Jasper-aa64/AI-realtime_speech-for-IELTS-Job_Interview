(function () {
  let csrfToken = null;

  async function ensureCsrfToken() {
    if (csrfToken) return csrfToken;
    try {
      const response = await fetch("/api/accounts/csrf/", { credentials: "same-origin" });
      const data = await response.json();
      csrfToken = data.csrfToken || null;
    } catch (_error) {
      csrfToken = null;
    }
    return csrfToken;
  }

  function getCsrfToken() {
    return csrfToken;
  }

  function resetCsrfToken() {
    csrfToken = null;
  }

  async function api(path, body = null, requestOptions = {}) {
    const method = requestOptions.method || (body !== null ? "POST" : "GET");
    const options = {
      method,
      credentials: "same-origin",
      headers: { ...(requestOptions.headers || {}) },
    };
    if (requestOptions.signal) options.signal = requestOptions.signal;
    if (body !== null) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    if (method !== "GET") {
      const token = await ensureCsrfToken();
      if (token) options.headers["X-CSRFToken"] = token;
    }
    const response = await fetch(path, options);
    const raw = await response.text();
    let payload = null;
    if (raw) {
      try {
        payload = JSON.parse(raw);
      } catch (_error) {
        if (!response.ok) throw new Error(`Request failed: ${response.status} ${response.statusText}`);
        throw new Error(`Invalid JSON response from ${path}`);
      }
    }
    if (!response.ok) {
      const message = payload?.message || payload?.error || `Request failed: ${response.status} ${response.statusText}`;
      const error = new Error(message);
      error.status = response.status;
      error.payload = payload;
      error.errors = payload?.errors || null;
      throw error;
    }
    return payload;
  }

  window.IELTSApiClient = {
    api,
    ensureCsrfToken,
    getCsrfToken,
    resetCsrfToken,
  };
})();
