# brainstorm: Django migration architecture

## Goal

Plan a staged migration from the current lightweight Python web backend and vanilla frontend toward a maintainable commercial-ready architecture using Django for the backend and, later, Vue 3 + Vite for the frontend. The immediate goal is planning and project scaffolding boundaries, not a risky big-bang rewrite.

## What I already know

* The current web backend is not Django or FastAPI. It is implemented in `web/ielts_server.py` using Python standard-library HTTP server primitives.
* The current frontend is vanilla HTML/CSS/JS under `web/static/`.
* Existing persisted business data is mostly local JSON reports under `reports/`, with some local SQLite-style billing/training state in the current backend.
* Recent product work added IELTS speaking reports and a `每日写作` feature with local JSON storage under `reports/writing/`.
* The user wants the current app to remain usable while a cleaner Django architecture is prepared.
* The user decided not to run parallel implementation for now.
* Login, registration, real payment, and production-grade user/account flows are not implemented yet.
* Copyright/ownership should be attributed to the project owner, not to AI-generated authorship.
* Long-term frontend direction is Vue 3 + Vite, separated from backend API delivery.
* Long-term backend direction is Django with app-based modular structure, MySQL-compatible database, Redis for cache/state, and indexes for core query paths.

## Assumptions (temporary)

* The first Django milestone should live in a separate directory, likely `backend_django/`, so it does not disrupt the current runnable app.
* The first migration pass should define models, APIs, settings, docs, and development structure before moving all legacy behavior.
* MySQL-compatible database support is acceptable for production planning, while SQLite may remain useful for local development if explicitly configured.
* Complex async task infrastructure can wait until after the core Django data model and API contracts are stable.

## Open Questions

* Which owner name and email should be used in copyright headers, README, and package metadata?

## Requirements (evolving)

* Keep the existing app functional during migration.
* Use Django app modules organized by business capability, not vague utility buckets.
* Prefer a staged migration over a big-bang rewrite.
* Do not let the Django migration and old frontend feature changes edit the same files at the same time.
* Define login/register/account ownership as first-class backend concepts.
* Define token wallet, billing ledger, and payment order concepts before integrating a real payment provider.
* Use database indexes for common user/report/writing/billing query paths.
* Keep AI fallback behavior explicit and distinguish generated results from default suggestions.
* Keep product-facing Chinese UX requirements in the API contract where relevant.
* Keep copyright attribution under the user/project owner identity.
* Every headless milestone must leave written documentation before moving to the next milestone.
* Each milestone document must record: goal, changed files/modules, key design decisions, verification commands/results, known gaps, rollback notes, and the recommended next milestone.

## Acceptance Criteria (evolving)

* [ ] A Django migration plan exists with clear phases and out-of-scope boundaries.
* [ ] The target backend module structure is documented.
* [ ] Initial database entities and indexes are listed before implementation.
* [ ] Initial API boundaries for speaking, writing, billing, account, and AI jobs are listed.
* [ ] The plan states how current JSON reports will be migrated or temporarily bridged.
* [ ] The plan states how the current app can keep running during migration.
* [ ] Copyright/ownership metadata is captured.
* [ ] Each completed headless milestone has a corresponding milestone note under this task directory or `docs/`.
* [ ] The final headless summary includes a follow-up validation plan and a ready-to-send prompt for the next headless run.

## Definition of Done (team quality bar)

* Tests added/updated when implementation starts.
* Python checks and Django checks pass when scaffold exists.
* Docs/notes updated if behavior or architecture changes.
* Rollout/rollback considered before replacing the old web app.
* No unrelated old-app code is rewritten during the planning-only stage.

## Out of Scope (explicit)

* No immediate full rewrite of `web/ielts_server.py`.
* No immediate Vue migration in the first backend planning task.
* No real payment provider integration until account and billing models are settled.
* No complex queue system in the first scaffold unless a clear blocking need appears.
* No production deployment change before the Django app can pass basic local verification.

## Technical Notes

* Current web entrypoint: `web/ielts_server.py`.
* Current frontend: `web/static/index.html`, `web/static/app.js`, `web/static/styles.css`.
* Current IELTS data: `data/ielts/`.
* Current report storage: `reports/`.
* Existing docs include `docs/IELTS_AI_PIPELINE_REFACTOR_PLAN.md`.
* Relevant Trellis specs currently document older backend conventions and should not be overwritten by the Django plan without a dedicated spec update.
* Documentation lookup was already performed for Django and Vue:
  * Django supports WSGI and ASGI; full async-stack benefits require ASGI.
  * Django has emerging task support in newer docs, but Redis plus a mature worker library remains a conservative production option when true background jobs are needed.
  * Vue docs recommend Vite/create-vue for modern Vue 3 scaffolding.

## Headless Milestone Documentation Rule

Each headless milestone must create or update a persistent note before proceeding. Preferred location:

* `.trellis/tasks/05-14-django-migration-architecture/research/` for architecture/research decisions.
* `.trellis/tasks/05-14-django-migration-architecture/` for milestone execution notes.
* `docs/` for project-facing architecture documents that should survive beyond this task.

Minimum section template:

* Goal
* Scope
* Files changed
* Design decisions
* Verification run
* Known gaps
* Rollback / compatibility notes
* Next recommended milestone

## Headless Follow-up Validation Plan

After the implementation headless run completes, the next immediate run should be an acceptance-focused headless run:

1. Read the latest milestone note and final summary from the previous run.
2. Inspect `git status --short` and classify changed files by milestone.
3. Run the available checks:
   * `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py`
   * `node --check web/static/app.js`
   * `python3 backend_django/manage.py check`
   * `python3 backend_django/manage.py makemigrations --check --dry-run`
   * `python3 backend_django/manage.py test`
4. If Django dependencies are unavailable, create or reuse `.venv-django`, install `requirements/local.txt`, and rerun Django checks.
5. Verify milestone documents exist and honestly describe changed files, decisions, verification, gaps, and next steps.
6. Review cross-layer flow for user ownership, long-running AI tasks, billing idempotency, report persistence, and refresh recovery.
7. Fix only clear defects discovered during validation; do not expand scope.
8. Update the milestone note with validation results and write the next recommended headless goal.

## Next Headless Prompt Template

Use this prompt after the current headless run finishes:

```text
继续 headless。先读取 .trellis 当前任务状态、上一阶段 milestone note、PRD、implement.jsonl/check.jsonl 和 git status。

你的目标不是重复上一轮，而是动态验收上一轮成果，并选择下一个最合理的阶段推进：
1. 如果上一轮有未完成或检查失败，先修复并补文档。
2. 如果上一轮完成但缺少阶段文档，先补齐文档。
3. 如果数据模型/迁移还不稳定，继续 Django 数据层和索引。
4. 如果数据层稳定，推进用户/权限/画像/计费的可恢复任务框架。
5. 如果长任务框架稳定，再推进写作/口语 API 迁移或旧前端桥接。

每完成一个阶段性目标都必须：
- 写阶段文档，包含目标、改动、决策、验证、已知问题、回滚说明、下一阶段建议。
- 运行可用检查。
- 不破坏旧 web/ielts_server.py 和 web/static 现有可用性，除非该阶段明确需要桥接。
- 遇到真实第三方密钥、破坏性数据库操作、产品取舍时停下汇报。

不要问我要不要继续；在合理范围内自己查资料、自己选择方案、自己执行，并在达到阶段目标后汇报。
```
