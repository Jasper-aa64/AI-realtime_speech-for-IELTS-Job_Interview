(function () {
  // detail.design's corner morph: spring stiffness 300, damping 30, mass 1 (ζ≈0.87), sampled over 500 ms.
  const SPRING = "linear(0, 0.0458, 0.1512, 0.2813, 0.4144, 0.5381, 0.6461, 0.7364, 0.8091, 0.8658, 0.9089, 0.9407, 0.9636, 0.9794, 0.99, 0.9968, 1.0009, 1.0031, 1.0041, 1.0043, 1.0041, 1.0036, 1.003, 1.0025, 1.0019, 1.0015, 1)";
  const OPEN_MS = 500;
  const CLOSE_MS = 380;
  const HOVER_IN_MS = 90;
  const HOVER_OUT_MS = 240;

  function reducedMotion() {
    try { return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true; } catch (_error) { return false; }
  }

  // A trigger grows into its card in place: the card shares the trigger's anchored corner, springs from the
  // trigger's size to its own, and its body cross-fades through a 4px blur. While open, `lift` (the fixed bar that
  // holds the card) is raised above every other layer so nothing on the page can paint over the card.
  function create({
    trigger, card, body = null, root = trigger, lift = null, anchor = "top-left",
    palette = null, onOpenChange = null, closedRadius = "10px", openRadius = "18px",
    closedBackground = "var(--switch-closed)", hoverBackground = "var(--switch-hover)",
  }) {
    let open = false;
    let timer = 0;
    let morph = null;
    let hoverOpened = false;
    if (!trigger || !card) return null;

    function place() {
      const from = trigger.getBoundingClientRect();
      if (anchor === "top-right") {
        card.style.left = "auto";
        card.style.right = `${Math.round(window.innerWidth - from.right)}px`;
      } else {
        card.style.right = "auto";
        card.style.left = `${Math.round(from.left)}px`;
      }
      card.style.top = `${Math.round(from.top)}px`;
      return from;
    }

    function animate(opening) {
      if (typeof card.animate !== "function") return null;
      morph?.cancel();
      const from = place();
      const to = card.getBoundingClientRect();
      // Closing holds its last frame ("forwards") until the card is hidden, so it never pops back to full size.
      const timing = (duration, extra = {}) => ({ duration, easing: SPRING, fill: opening ? "none" : "forwards", ...extra });
      if (reducedMotion()) {
        morph = card.animate([{ opacity: opening ? 0 : 1 }, { opacity: opening ? 1 : 0 }], timing(120, { easing: "ease-out" }));
        return morph;
      }
      // Opening starts from the hovered trigger's tint; closing ends on the plain surface so the hand-off is seamless.
      const closed = { width: `${from.width}px`, height: `${from.height}px`, borderRadius: closedRadius, backgroundColor: opening ? hoverBackground : closedBackground, borderColor: "transparent", boxShadow: "0 0 0 rgba(0,0,0,0)" };
      const full = { width: `${to.width}px`, height: `${to.height}px`, borderRadius: openRadius, backgroundColor: "var(--switch-bg)", borderColor: "var(--switch-line)", boxShadow: "var(--switch-shadow)" };
      morph = card.animate(opening ? [closed, full] : [full, closed], timing(opening ? OPEN_MS : CLOSE_MS));
      body?.getAnimations?.().forEach((animation) => animation.cancel());
      body?.animate?.(
        opening ? [{ opacity: 0, filter: "blur(4px)" }, { opacity: 1, filter: "blur(0px)" }] : [{ opacity: 1, filter: "blur(0px)" }, { opacity: 0, filter: "blur(4px)" }],
        { duration: opening ? 200 : 100, delay: opening ? 60 : 0, easing: "ease-out", fill: opening ? "backwards" : "forwards" },
      );
      return morph;
    }

    function set(value, { restoreFocus = false, viaHover = false } = {}) {
      window.clearTimeout?.(timer);
      if (open === value) {
        if (!value && restoreFocus) trigger.focus();
        return;
      }
      open = value;
      hoverOpened = value && viaHover;
      trigger.setAttribute("aria-expanded", String(value));
      root.classList?.toggle("is-open", value);
      if (value) {
        lift?.classList.add("has-corner-morph-open");
        palette?.();
        card.hidden = false;
        card.inert = false;
        onOpenChange?.(true);
      }
      const animation = animate(value);
      if (!value) {
        onOpenChange?.(false);
        const finish = () => {
          if (open) return;
          card.hidden = true;
          card.inert = false;
          animation?.cancel();
          body?.getAnimations?.().forEach((item) => item.cancel());
          lift?.classList.remove("has-corner-morph-open");
        };
        if (animation) { card.inert = true; animation.finished.then(finish, () => {}); } else finish();
        if (restoreFocus) trigger.focus();
      }
    }

    // Pointer intent opens it like detail.design; a short grace period lets the cursor travel into the card.
    const zones = root === trigger ? [trigger, card] : [root];
    zones.forEach((zone) => {
      zone.addEventListener("pointerenter", (event) => {
        if (event.pointerType !== "mouse") return;
        window.clearTimeout?.(timer);
        palette?.();
        if (!open) timer = window.setTimeout?.(() => set(true, { viaHover: true }), HOVER_IN_MS);
      });
      zone.addEventListener("pointerleave", (event) => {
        if (event.pointerType !== "mouse") return;
        if (zones.some((other) => other !== zone && other.contains?.(event.relatedTarget))) return;
        window.clearTimeout?.(timer);
        if (open) timer = window.setTimeout?.(() => set(false), HOVER_OUT_MS);
      });
    });
    document.addEventListener("pointerdown", (event) => {
      if (open && !root.contains(event.target) && !card.contains(event.target)) set(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && open) set(false, { restoreFocus: true });
    });
    window.addEventListener?.("resize", () => set(false));

    return {
      open: (options = {}) => set(true, options),
      close: (options = {}) => set(false, options),
      toggle: () => set(!open),
      isOpen: () => open,
      openedByHover: () => hoverOpened,
    };
  }

  window.IELTSCornerMorph = { create, SPRING, reducedMotion };
})();
