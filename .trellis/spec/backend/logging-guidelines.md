# Logging Guidelines

> How logging is done in this project.

---

## Overview

<!--
Document your project's logging conventions here.

Questions to answer:
- What logging library do you use?
- What are the log levels and when to use each?
- What should be logged?
- What should NOT be logged (PII, secrets)?
-->

(To be filled by the team)

---

## Log Levels

<!-- When to use each level: debug, info, warn, error -->

(To be filled by the team)

---

## Structured Logging

<!-- Log format, required fields -->

(To be filled by the team)

---

## What to Log

<!-- Important events to log -->

(To be filled by the team)

---

## What NOT to Log

<!-- Sensitive data, PII, secrets -->

(To be filled by the team)

## Current AI Task Rule

- For Django AI task work, log only safe routing facts such as `task_id`,
  `task_type`, durable `provider`, adapter name, and terminal status.
- Never log provider secret values, raw API-key env vars, or copied secret
  strings from the process environment.
- When documenting provider configuration, keep only placeholder env-var names
  such as `CODEX_API_KEY`, `OPENAI_API_KEY`, and `ANTHROPIC_API_KEY`.
