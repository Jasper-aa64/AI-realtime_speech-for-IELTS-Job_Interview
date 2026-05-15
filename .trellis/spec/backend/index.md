# Backend Development Guidelines

> Best practices for backend development in this project.

---

## Overview

This directory contains guidelines for backend development. Fill in each file with your project's specific conventions.

---

## Project Conventions

### Convention: Keep scoring calibration out of report payloads

**What**: The backend must not emit `china_explanation` or other local-language scoring explanation blocks in scored reports. China-specific IELTS calibration belongs in `data/ielts/prompts/scorer_system.md`, and the official score stays in `ielts_score`.

**Why**: The product uses China-candidate evidence to make the scoring prompt more precise, not to show a separate or vague explanation section to the user.

**Example**:
```python
report["ielts_score"] = score
```

**Related**: Frontend report rendering should show official score, per-turn transcript, Band 7 spoken version, AI guidance, and rubric reference only.

### Convention: Keep weak-item training internal

**What**: `training_observations` may be saved to power weak-question replay and frequency adjustments, but report UI should not expose a `弱题训练` block.

**Why**: Weak-item records are scheduling and training metadata. Showing them in the report duplicates feedback and confuses the role of AI guidance.

**Example**:
```python
attempt["training_observations"] = state.training.record_attempt(attempt)
```

**Related**: Settings/training screens may expose weak-item queues separately when the user explicitly opens training tools.

### Convention: Generate IELTS coaching in Chinese with learner context

**What**: Attempt reports may include `learning_profile` and `personalized_coaching` derived from the current attempt plus weak-item history. User-facing AI coaching should be natural Chinese for mainland IELTS learners, with evidence, the reason for the issue, a replacement expression or structure, and a next practice action.

**Why**: The product is for Chinese IELTS Speaking learners. English-only or generic coaching reads like a model artifact and does not help the user change their speaking habits.

**Example**:
```python
attempt["learning_profile"] = build_learning_profile(state, attempt, score)
attempt["personalized_coaching"] = build_personalized_coaching(profile, attempt, score)
```

**Related**: Weak-item scheduling data stays internal. The report may use weak history as evidence for personalized advice, but it must not render the scheduler itself as a separate report module.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Module organization and file layout | To fill |
| [Database Guidelines](./database-guidelines.md) | ORM patterns, queries, migrations | AI task lifecycle filled |
| [Error Handling](./error-handling.md) | Error types, handling strategies | AI task lifecycle filled |
| [Quality Guidelines](./quality-guidelines.md) | Code standards, forbidden patterns | AI task lifecycle filled |
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
