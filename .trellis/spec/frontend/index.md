# Frontend Development Guidelines

> Best practices for frontend development in this project.

---

## Overview

This directory contains guidelines for frontend development. Fill in each file with your project's specific conventions.

## Project Conventions

### Convention: Render local explanation as guidance, not scoring

**What**: The frontend can render a `china_explanation` section in the report, but it must not present it as a separate band or alternate score.

**Why**: Users need a Chinese explanation of the official IELTS result, not a second scoring system.

**Example**:
```js
const chinaExplanation = attempt.china_explanation || {};
```

**Related**: Keep pronunciation estimate labels explicit when no audio analysis is available.

### Convention: Use natural Chinese labels in the explanation block

**What**: Report copy for domestic learners should use natural labels such as `中文说明`, `常见短板`, and `下一步`, with human fallback text instead of `暂无`.

**Why**: The explanation block should read like a real IELTS prep product for Chinese users. Direct translations and empty placeholders make the UI feel broken or artificial even when the score data is correct.

**Example**:
```js
function chinaExplanationBlock(item = {}) {
  return `
    <div class="detail-section china-explanation">
      <h3>${escapeHtml(item.title || "中文说明")}</h3>
      <h4>常见短板</h4>
      <ul>${weakPoints || "<li>暂未发现明显短板</li>"}</ul>
      <h4>下一步</h4>
      <ul>${nextSteps || "<li>先把回答说完整，再逐步增加例子和衔接</li>"}</ul>
    </div>
  `;
}
```

**Related**: Keep the official band labels and pronunciation estimate labels explicit.

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
