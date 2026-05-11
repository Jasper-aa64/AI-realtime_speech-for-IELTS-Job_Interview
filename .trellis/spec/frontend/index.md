# Frontend Development Guidelines

> Best practices for frontend development in this project.

---

## Overview

This directory contains guidelines for frontend development. Fill in each file with your project's specific conventions.

## Project Conventions

### Convention: Do not render calibration text in reports

**What**: The frontend must not render `china_explanation`, `中文说明`, or similar local scoring explanation sections in attempt reports.

**Why**: China-candidate calibration should improve scorer prompt accuracy, not appear as vague report copy.

**Example**:
```js
// Report body: score summary, turn table, Band 7 spoken version, AI guidance, rubric reference.
```

**Related**: Keep pronunciation estimate labels explicit when no audio analysis is available.

### Convention: Keep weak training out of attempt reports

**What**: The report view must not render a `弱题训练` section from `training_observations`.

**Why**: Weak-item observations are for replay frequency and background training queues. User-facing improvement advice belongs in AI guidance and the rubric reference section.

**Example**:
```js
${turnTableSection(attempt, turns, isP2)}
```

**Related**: Keep the official band labels and pronunciation estimate labels explicit.

### Convention: Keep global account/settings controls in the lower-left nav

**What**: The sidebar should reserve its bottom area for global controls: typeface switcher, Settings, and candidate identity. Primary practice navigation stays above.

**Why**: This matches common desktop app layouts and keeps account/preferences separate from practice modes.

**Example**:
```html
<div class="nav-bottom">
  <div class="font-tool">...</div>
  <button data-view="settings">Settings</button>
  <label class="nav-user">...</label>
</div>
```

**Related**: Typeface choice is a local UI preference persisted in `localStorage`, not a backend setting.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Module organization and file layout | To fill |
| [Component Guidelines](./component-guidelines.md) | Component patterns, props, composition | To fill |
| [Hook Guidelines](./hook-guidelines.md) | Custom hooks, data fetching patterns | To fill |
| [State Management](./state-management.md) | Local state, global state, server state | To fill |
| [Quality Guidelines](./quality-guidelines.md) | Code standards, forbidden patterns | To fill |
| [Type Safety](./type-safety.md) | Type patterns, validation | To fill |

---

## How to Fill These Guidelines

For each guideline file:

1. Document your project's **actual conventions** (not ideals)
2. Include **code examples** from your codebase
3. List **forbidden patterns** and why
4. Add **common mistakes** your team has made

The goal is to help AI assistants and new team members understand how YOUR project works.

---

**Language**: All documentation should be written in **English**.
