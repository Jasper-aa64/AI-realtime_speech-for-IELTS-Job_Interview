// Home dashboard: the feature carousel and the practice-stats panel in the home hero.
// Read-only: it only calls existing GET endpoints and mirrors the sidebar due badges.
(function () {
  const panel = document.getElementById("homePanel");
  if (!panel) return;

  /* ---------- Carousel ----------
     One slide shows at a time; the active progress segment fills over 5s (CSS animation)
     and its animationend advances to the next slide. Hover/focus pauses it. */
  const show = panel.querySelector("[data-hx-show]");
  if (show) {
    const slides = [...show.querySelectorAll(".hx-slide")];
    const segs = [...show.querySelectorAll(".hx-seg")];
    const count = show.querySelector("[data-hx-count]");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let index = 0;

    if (reduce) show.classList.add("no-auto");

    const go = (next) => {
      index = (next + slides.length) % slides.length;
      slides.forEach((slide, i) => {
        const on = i === index;
        slide.classList.toggle("is-active", on);
        slide.toggleAttribute("aria-hidden", !on);
        slide.tabIndex = on ? 0 : -1;
      });
      segs.forEach((seg, i) => {
        seg.classList.toggle("is-on", i === index);
        seg.classList.toggle("is-done", i < index);
        // Restart the fill animation on the newly active segment.
        const bar = seg.querySelector("i");
        if (bar && i === index) {
          bar.style.animation = "none";
          void bar.offsetWidth;
          bar.style.animation = "";
        }
      });
      if (count) count.textContent = String(index + 1).padStart(2, "0");
    };

    segs.forEach((seg, i) => {
      seg.addEventListener("click", () => go(i));
      seg.querySelector("i")?.addEventListener("animationend", () => {
        if (i === index) go(index + 1);
      });
    });
    show.querySelectorAll("[data-step]").forEach((btn) => {
      btn.addEventListener("click", () => go(index + Number(btn.dataset.step || 1)));
    });

    const hold = (on) => show.classList.toggle("is-paused", on);
    show.addEventListener("pointerenter", () => hold(true));
    show.addEventListener("pointerleave", () => hold(false));
    show.addEventListener("focusin", () => hold(true));
    show.addEventListener("focusout", () => hold(false));
    // Only run while the home view is on screen.
    const syncVisible = () => show.classList.toggle("is-hidden", panel.classList.contains("hidden") || document.hidden);
    document.addEventListener("visibilitychange", syncVisible);
    new MutationObserver(syncVisible).observe(panel, { attributes: true, attributeFilter: ["class"] });
    syncVisible();
  }

  /* ---------- Stats ---------- */
  const $ = (sel) => panel.querySelector(sel);
  const setText = (sel, value) => {
    const el = $(sel);
    if (el) el.textContent = value;
  };
  const getJSON = async (url) => {
    try {
      const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
      return response.ok ? await response.json() : null;
    } catch (_error) {
      return null;
    }
  };

  const renderDate = (iso) => {
    const el = $('[data-hx-stat="last"]');
    if (!el) return;
    const date = iso ? new Date(iso) : null;
    if (!date || Number.isNaN(date.getTime())) {
      el.textContent = "–";
      return;
    }
    const pad = (n) => String(n).padStart(2, "0");
    el.innerHTML = `<time datetime="${date.toISOString().slice(0, 10)}"><span class="hx-stat-year">${date.getFullYear()}</span>${pad(date.getMonth() + 1)}<span class="hx-stat-sep">·</span>${pad(date.getDate())}</time>`;
  };

  let loading = false;
  async function refreshStats() {
    if (loading || panel.classList.contains("hidden")) return;
    loading = true;
    const [history, writing, bank] = await Promise.all([
      getJSON("/api/history"),
      getJSON("/api/writing/summary"),
      getJSON("/api/question-bank/summary"),
    ]);
    loading = false;

    const items = Array.isArray(history?.items) ? history.items : null;
    setText('[data-hx-stat="speaking"]', items ? String(items.length) : "–");
    const total = writing?.stats?.total_entries;
    setText('[data-hx-stat="writing"]', Number.isFinite(total) ? String(total) : "–");

    // Most recent of the latest speaking report and the latest writing entry.
    const stamps = [];
    if (items?.[0]?.timestamp) stamps.push(items[0].timestamp);
    const recent = writing?.recent_entries?.[0]?.display_time;
    if (recent) stamps.push(recent.replace(" ", "T"));
    const latest = stamps.map((s) => new Date(s)).filter((d) => !Number.isNaN(d.getTime())).sort((a, b) => b - a)[0];
    renderDate(latest ? latest.toISOString() : null);

    if (bank) {
      setText('[data-hx-bank="p1"]', bank.part1_count ?? "");
      setText('[data-hx-bank="p2"]', bank.part2_count ?? "");
      setText('[data-hx-bank="p3"]', bank.part3_follow_up_count ?? "");
      if (bank.active_scope_label) setText('[data-hx-bank="label"]', bank.active_scope_label);
    }
  }

  /* Due counts mirror the sidebar badges, which the app already keeps current. */
  const dueTargets = [...panel.querySelectorAll("[data-hx-due]")];
  const syncDue = () => {
    dueTargets.forEach((sup) => {
      const dot = document.getElementById(sup.dataset.hxDue);
      const n = dot && !dot.classList.contains("hidden") ? Number(dot.getAttribute("data-count") || 0) : 0;
      sup.textContent = n > 0 ? String(n) : "";
      sup.closest(".hx-chip")?.classList.toggle("is-due", n > 0);
    });
  };
  dueTargets.forEach((sup) => {
    const dot = document.getElementById(sup.dataset.hxDue);
    if (dot) new MutationObserver(syncDue).observe(dot, { attributes: true, attributeFilter: ["class", "data-count"] });
  });
  syncDue();

  new MutationObserver(() => {
    if (!panel.classList.contains("hidden")) refreshStats();
  }).observe(panel, { attributes: true, attributeFilter: ["class"] });
  if (document.readyState === "complete") refreshStats();
  else window.addEventListener("load", refreshStats);
})();
