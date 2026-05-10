# Backend Development Guidelines

> Best practices for backend development in this project.

---

## Overview

This directory contains guidelines for backend development. Fill in each file with your project's specific conventions.

## Project Conventions

### Convention: Keep IELTS scoring and local explanation separate

**What**: The backend may emit a `china_explanation` block in scored reports, but the official IELTS score stays in `ielts_score`.

**Why**: This prevents a local-language explanation layer from being mistaken for a second scoring system.

**Example**:
```python
report["ielts_score"] = score
report["china_explanation"] = build_china_explanation(score, pronunciation)
```

**Related**: Frontend report rendering should display the explanation block as guidance, not as a band conversion.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Module organization and file layout | To fill |
| [Database Guidelines](./database-guidelines.md) | ORM patterns, queries, migrations | To fill |
| [Error Handling](./error-handling.md) | Error types, handling strategies | To fill |
| [Quality Guidelines](./quality-guidelines.md) | Code standards, forbidden patterns | To fill |
| [Logging Guidelines](./logging-guidelines.md) | Structured logging, log levels | To fill |

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
