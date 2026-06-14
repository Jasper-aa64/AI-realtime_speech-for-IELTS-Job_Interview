(function () {
  "use strict";

  function createWritingPromptImagePreloader(options) {
    const {
      state,
      scheduleIdleTask,
      imagePreloadLimit = 2,
    } = options || {};
    if (!state?.writing || typeof scheduleIdleTask !== "function") {
      throw new Error("Writing image preloader requires writing state and scheduleIdleTask.");
    }

    function imageUrls(prompts = []) {
      return prompts
        .map((prompt) => String(prompt?.image_url || "").trim())
        .filter(Boolean);
    }

    function thumbUrlFor(imageUrl = "") {
      const raw = String(imageUrl || "").trim();
      if (!raw.startsWith("/assets/")) return raw;
      return `/assets/thumbs/${raw.slice("/assets/".length)}.webp`;
    }

    function prime(url, primeOptions = {}) {
      const imageUrl = String(url || "").trim();
      if (!imageUrl) return false;
      // Originals and thumbnails are tracked in separate dedup sets so warming
      // one never blocks the other for the same prompt.
      const original = Boolean(primeOptions.original);
      const seen = original ? state.writing.promptOriginalPreloads : state.writing.promptImagePreloads;
      const promises = original ? state.writing.promptOriginalPreloadPromises : state.writing.promptImagePreloadPromises;
      if (seen.has(imageUrl)) return false;
      const preloadUrl = original ? imageUrl : thumbUrlFor(imageUrl);
      seen.add(imageUrl);
      const image = new Image();
      image.decoding = "async";
      image.loading = primeOptions.priority === "low" ? "lazy" : "eager";
      if ("fetchPriority" in image) image.fetchPriority = primeOptions.priority === "low" ? "low" : "high";
      const loaded = new Promise((resolve) => {
        image.onload = () => resolve({ url: imageUrl, ok: true });
        image.onerror = () => resolve({ url: imageUrl, ok: false });
      });
      const promise = loaded.then(async (result) => {
        if (result.ok && typeof image.decode === "function") {
          await image.decode().catch(() => null);
        }
        if (result.ok) {
          // Record the actually-loaded URL (thumb or original) so the picker
          // can render already-decoded images instantly, without a blank
          // opacity fade-in on every re-render.
          if (!state.writing.promptImageReadyUrls) state.writing.promptImageReadyUrls = new Set();
          state.writing.promptImageReadyUrls.add(preloadUrl);
        }
        return result;
      });
      promises.set(imageUrl, promise);
      image.src = preloadUrl;
      return true;
    }

    // Preload an original-resolution image (low priority by default) so the
    // full-size viewer ("点开看") opens instantly.
    function primeOriginal(url, priority = "low") {
      return prime(url, { original: true, priority });
    }

    function queue(prompts = [], queueOptions = {}) {
      const offset = Math.max(0, Number(queueOptions.offset || 0));
      const limit = Number.isFinite(Number(queueOptions.limit)) ? Math.max(0, Number(queueOptions.limit)) : Infinity;
      let queued = 0;
      for (const url of imageUrls(prompts).slice(offset)) {
        if (queued >= limit) break;
        if (state.writing.promptImagePreloads.has(url) || state.writing.promptImagePreloadQueued.has(url)) continue;
        state.writing.promptImagePreloadQueued.add(url);
        state.writing.promptImagePreloadQueue.push(url);
        queued += 1;
      }
    }

    // Push prompts to the FRONT of the queue without discarding the existing
    // backlog, so nearby thumbnails get priority while warmAll keeps running.
    function queueFront(prompts = [], queueOptions = {}) {
      const limit = Number.isFinite(Number(queueOptions.limit)) ? Math.max(0, Number(queueOptions.limit)) : Infinity;
      const urls = [];
      let queued = 0;
      for (const url of imageUrls(prompts)) {
        if (queued >= limit) break;
        if (state.writing.promptImagePreloads.has(url) || state.writing.promptImagePreloadQueued.has(url)) continue;
        state.writing.promptImagePreloadQueued.add(url);
        urls.push(url);
        queued += 1;
      }
      if (urls.length) state.writing.promptImagePreloadQueue.unshift(...urls);
    }

    function canUseBackgroundPreload() {
      const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
      if (connection?.saveData) return false;
      const effectiveType = String(connection?.effectiveType || "").toLowerCase();
      return effectiveType !== "slow-2g" && effectiveType !== "2g";
    }

    function canWarm(options = {}) {
      if (document.visibilityState === "hidden") return false;
      return options.anyView || state.view === "writing";
    }

    function scheduleNearby(prompt) {
      if (!prompt || prompt.task_type !== "task1_academic") return;
      if (!canUseBackgroundPreload()) return;
      const prompts = state.writing.prompts.task1_academic || [];
      if (!prompts.length) return;
      const currentIndex = prompts.findIndex((item) => item.id === prompt.id);
      if (currentIndex < 0) return;
      const nearbyPrompts = prompts.slice(currentIndex + 1, currentIndex + 1 + imagePreloadLimit);
      const currentImageUrl = String(prompt.image_url || "").trim();
      const preloadSource = `${prompt.id || currentIndex}:${currentImageUrl}`;
      if (state.writing.nearbyPromptImagePreloadSource === preloadSource) {
        if (canWarm() && state.writing.promptImagePreloadQueue.length) drain();
        return;
      }
      state.writing.nearbyPromptImagePreloadSource = preloadSource;
      const preloadAfterCurrent = () => {
        if (!canWarm()) return;
        // Give nearby thumbnails priority without wiping the warmAll backlog.
        queueFront(nearbyPrompts, { limit: imagePreloadLimit });
        // Warm the ORIGINAL-resolution images for the current prompt and the
        // nearby ones (low priority) so "点开看" opens instantly. These run
        // outside the thumbnail queue.
        if (currentImageUrl) primeOriginal(currentImageUrl, "low");
        imageUrls(nearbyPrompts).slice(0, imagePreloadLimit).forEach((nearbyUrl) => primeOriginal(nearbyUrl, "low"));
        drain();
      };
      const currentPromise = currentImageUrl ? state.writing.promptImagePreloadPromises.get(currentImageUrl) : null;
      if (currentPromise) {
        currentPromise.finally(() => scheduleIdleTask(preloadAfterCurrent, 250));
      } else {
        scheduleIdleTask(preloadAfterCurrent, 250);
      }
    }

    function drain(options = {}) {
      if (state.writing.promptImagePreloadScheduled) return;
      if (!state.writing.promptImagePreloadQueue.length) return;
      state.writing.promptImagePreloadScheduled = true;
      scheduleIdleTask(() => {
        state.writing.promptImagePreloadScheduled = false;
        if (!canWarm(options)) {
          if (document.visibilityState === "hidden") {
            const resume = () => {
              document.removeEventListener("visibilitychange", resume);
              drain(options);
            };
            document.addEventListener("visibilitychange", resume, { once: true });
          }
          return;
        }
        while (state.writing.promptImagePreloadActive < imagePreloadLimit && state.writing.promptImagePreloadQueue.length) {
          const url = state.writing.promptImagePreloadQueue.shift();
          state.writing.promptImagePreloadQueued.delete(url);
          if (!url || state.writing.promptImagePreloads.has(url)) continue;
          state.writing.promptImagePreloadActive += 1;
          const started = prime(url, { priority: "low" });
          const promise = state.writing.promptImagePreloadPromises.get(url) || Promise.resolve();
          promise.finally(() => {
            state.writing.promptImagePreloadActive = Math.max(0, state.writing.promptImagePreloadActive - 1);
            drain(options);
          });
          if (!started) {
            state.writing.promptImagePreloadActive = Math.max(0, state.writing.promptImagePreloadActive - 1);
          }
        }
        if (state.writing.promptImagePreloadQueue.length) drain(options);
      }, 250);
    }

    // Warm every prompt thumbnail in the background (low priority, throttled
    // by drain) so the picker grid is already populated when it opens.
    function warmAll(prompts = []) {
      if (!canUseBackgroundPreload()) return;
      queue(prompts);
      drain({ anyView: true });
    }

    function prefetchHints(prompts = [], options = {}) {
      if (!canUseBackgroundPreload()) return 0;
      const limit = Number.isFinite(Number(options.limit)) ? Math.max(0, Number(options.limit)) : 12;
      let added = 0;
      imageUrls(prompts).slice(0, limit).forEach((imageUrl) => {
        const href = thumbUrlFor(imageUrl);
        const exists = Array.from(document.head.querySelectorAll('link[rel="prefetch"][as="image"]'))
          .some((link) => link.getAttribute("href") === href);
        if (!href || exists) return;
        const link = document.createElement("link");
        link.rel = "prefetch";
        link.as = "image";
        link.href = href;
        document.head.appendChild(link);
        added += 1;
      });
      return added;
    }

    async function ensureReady(url) {
      const imageUrl = String(url || "").trim();
      if (!imageUrl) return;
      prime(imageUrl);
      await state.writing.promptImagePreloadPromises.get(imageUrl);
    }

    return {
      canWarmWritingPromptImages: canWarm,
      drainWritingPromptImagePreloadQueue: drain,
      ensureWritingPromptImageReady: ensureReady,
      primeWritingPromptImage: prime,
      primeWritingPromptOriginalImage: primeOriginal,
      prefetchWritingPromptImageHints: prefetchHints,
      scheduleNearbyWritingPromptImagePreload: scheduleNearby,
      warmAllWritingPromptImages: warmAll,
      writingPromptThumbUrl: thumbUrlFor,
    };
  }

  window.IELTSWritingImagePreload = { createWritingPromptImagePreloader };
})();
