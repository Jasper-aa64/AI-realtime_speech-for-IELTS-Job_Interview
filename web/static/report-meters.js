// Report score meters: reads the band numbers the app already rendered and exposes
// them as CSS variables (--band / --score, 0–9) so styles.css can draw the overall
// ring and the per-criterion bars. Purely presentational; it never changes content.
(function () {
  const BAND_SELECTOR = ".speaking-score-summary-band, .writing-score-summary-band";
  const CELL_SELECTOR = ".speaking-score-summary-grid .score-cell, .writing-score-summary-grid .score-cell";

  const readBand = (text) => {
    const match = String(text || "").match(/\d+(?:\.\d+)?/);
    const value = match ? Number(match[0]) : NaN;
    return Number.isFinite(value) && value >= 0 && value <= 9 ? value : null;
  };

  const apply = (el, prop) => {
    const strong = el.querySelector("strong");
    const value = readBand(strong?.textContent);
    if (value === null) {
      el.style.removeProperty(prop);
      el.classList.remove("has-meter");
      return;
    }
    if (el.style.getPropertyValue(prop) !== String(value)) el.style.setProperty(prop, String(value));
    // The ring prints the bare number from this attribute (centred by CSS).
    if (strong && strong.dataset.band !== String(value)) strong.dataset.band = String(value);
    el.classList.add("has-meter");
  };

  let queued = false;
  const scan = () => {
    queued = false;
    document.querySelectorAll(BAND_SELECTOR).forEach((el) => apply(el, "--band"));
    document.querySelectorAll(CELL_SELECTOR).forEach((el) => apply(el, "--score"));
  };
  const schedule = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(scan);
  };

  const roots = ["detailPanel", "writingReportDetail"].map((id) => document.getElementById(id)).filter(Boolean);
  roots.forEach((root) => new MutationObserver(schedule).observe(root, { childList: true, subtree: true }));
  schedule();
})();
