# Brainstorm Practice and Particle Decoration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add direct new-tab P2 practice from Brainstorm and a lightweight animated square-particle accent.

**Architecture:** Extend the existing URL router with P2 cue/autostart fields, reuse the existing `startPractice()` path, and keep visual initialization inside the corpus controller. Vendor particles.js and the Lucide play asset with their licenses.

**Tech Stack:** Vanilla JavaScript, CSS, particles.js, Lucide SVG asset, Node test runner.

---

### Task 1: Route and direct-practice control

**Files:** `web/static/view-router.js`, `web/static/app.js`, `web/static/corpus-takeaway.js`, `web/static/styles.css`, `scripts/test_p2_brainstorm_practice_launch.mjs`

- [ ] Add a failing source regression test for URL fields, the play control, new-tab launch, autostart, and centered sizing.
- [ ] Run it and verify failure.
- [ ] Implement the route fields and reuse `state.p2Corpus.pinnedCueId` plus `startPractice()`.
- [ ] Add the circular Lucide-backed control and click handler.
- [ ] Run the test and JS syntax checks.

### Task 2: Particle decoration

**Files:** `web/static/vendor/particles.min.js`, `web/static/vendor/particles.LICENSE`, `web/static/corpus-takeaway.js`, `web/static/styles.css`, `web/static/index.html`, `scripts/test_p2_brainstorm_practice_launch.mjs`

- [ ] Add failing assertions for the particle host, one-time initialization, non-interactive canvas, dark mode, and reduced motion.
- [ ] Vendor particles.js from its official MIT repository.
- [ ] Initialize square particles only when the Brainstorm entry card is rendered.
- [ ] Add bounded responsive styling and bump cache versions.
- [ ] Run focused tests, JS checks, Django check, and diff-check.
