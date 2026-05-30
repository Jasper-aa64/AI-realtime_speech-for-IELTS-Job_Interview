(function () {
  function createViewRouter({ state, viewCopy }) {
    if (!state || !viewCopy) {
      throw new Error("IELTSViewRouter requires state and viewCopy.");
    }

    function requestedUrlView() {
      try {
        const view = new URLSearchParams(window.location.search).get("view");
        return viewCopy[view] ? view : "";
      } catch (_error) {
        return "";
      }
    }

    function requestedRouteState() {
      try {
        const params = new URLSearchParams(window.location.search);
        const view = params.get("view");
        return {
          view: viewCopy[view] ? view : "",
          writingTask: params.get("task") || "",
          writingPromptId: params.get("prompt") || "",
          speakingReportId: params.get("report") || "",
          writingReportId: params.get("writing_report") || "",
          writingEntryId: params.get("writing_entry") || "",
        };
      } catch (_error) {
        return {
          view: "",
          writingTask: "",
          writingPromptId: "",
          speakingReportId: "",
          writingReportId: "",
          writingEntryId: "",
        };
      }
    }

    function requestedStandaloneView() {
      const view = requestedUrlView();
      return ["p1Corpus", "p2Corpus"].includes(view) ? view : "";
    }

    function viewUrl(view) {
      const url = new URL(window.location.href);
      url.search = "";
      url.hash = "";
      url.searchParams.set("view", viewCopy[view] ? view : "home");
      return url.toString();
    }

    function isNewTabNavigationEvent(event) {
      return Boolean(event?.metaKey || event?.ctrlKey || event?.button === 1);
    }

    function openViewInNewTabForModifier(event, view) {
      if (!isNewTabNavigationEvent(event)) return false;
      window.open(viewUrl(view), "_blank", "noopener");
      event.preventDefault();
      event.stopPropagation();
      return true;
    }

    function updateViewUrl(view, options = {}) {
      if (!window.history?.replaceState || !viewCopy[view] || state.routeApplying) return;
      const url = new URL(window.location.href);
      if (view === "home") {
        url.searchParams.delete("view");
      } else {
        url.searchParams.set("view", view);
      }
      if (view === "writing") {
        url.searchParams.set("task", state.writing.taskType || "task1_academic");
        if (state.writing.prompt?.id) url.searchParams.set("prompt", state.writing.prompt.id);
        else url.searchParams.delete("prompt");
        const writingEntryId = state.writing.entry?.id || state.writing.requestedEntryId || "";
        if (writingEntryId) url.searchParams.set("writing_entry", writingEntryId);
        else url.searchParams.delete("writing_entry");
        url.searchParams.delete("report");
        url.searchParams.delete("writing_report");
      } else if (view === "history") {
        if (state.activeHistoryId) url.searchParams.set("report", state.activeHistoryId);
        else url.searchParams.delete("report");
        url.searchParams.delete("task");
        url.searchParams.delete("prompt");
        url.searchParams.delete("writing_report");
        url.searchParams.delete("writing_entry");
      } else if (view === "writingReports") {
        if (state.writing.activeReportId) url.searchParams.set("writing_report", state.writing.activeReportId);
        else url.searchParams.delete("writing_report");
        url.searchParams.delete("task");
        url.searchParams.delete("prompt");
        url.searchParams.delete("report");
        url.searchParams.delete("writing_entry");
      } else {
        url.searchParams.delete("task");
        url.searchParams.delete("prompt");
        url.searchParams.delete("report");
        url.searchParams.delete("writing_report");
        url.searchParams.delete("writing_entry");
      }
      const nextUrl = url.toString();
      if (nextUrl === window.location.href) return;
      const method = options.replace ? "replaceState" : "pushState";
      window.history[method]({ view }, "", nextUrl);
    }

    function syncUrlForCurrentState(options = {}) {
      updateViewUrl(state.view, options);
    }

    function writingPromptDeepLink(prompt) {
      const url = new URL(window.location.href);
      url.search = "";
      url.hash = "";
      url.searchParams.set("view", "writing");
      url.searchParams.set("task", prompt?.task_type || "task2");
      if (prompt?.id) url.searchParams.set("prompt", prompt.id);
      return url.toString();
    }

    function writingEntryEditUrl(entry = {}) {
      const url = new URL(window.location.href);
      url.search = "";
      url.hash = "";
      url.searchParams.set("view", "writing");
      url.searchParams.set("task", entry.task_type || state.writing.taskType || "task1_academic");
      if (entry.prompt_id) url.searchParams.set("prompt", entry.prompt_id);
      if (entry.id) url.searchParams.set("writing_entry", entry.id);
      return url.toString();
    }

    return {
      requestedUrlView,
      requestedRouteState,
      requestedStandaloneView,
      viewUrl,
      isNewTabNavigationEvent,
      openViewInNewTabForModifier,
      updateViewUrl,
      syncUrlForCurrentState,
      writingPromptDeepLink,
      writingEntryEditUrl,
    };
  }

  window.IELTSViewRouter = {
    createViewRouter,
  };
})();
