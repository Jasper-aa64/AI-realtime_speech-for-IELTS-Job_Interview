# Scheduled Claude Code Task

Project root:

```text
C:\Users\liangjunming\Desktop\AI_Project
```

Run autonomously. Do not ask the user questions. The user is asleep.

Use Claude Code with Opus and maximum effort. Work carefully, verify changes, and keep going until the concrete UI task is complete. Then continue the existing refactoring plan.

## Primary UI Task

Resume and finish the current in-progress task in this IELTS Studio repo:

- Redesign the Part 1 Library / P1 短答语料库 topic-card UI.
- Target card example:

  ```text
  Ambition And Dreams 0/4

  Q1 What was your childhood dream?
  Q2 Are you the kind of person who sticks to dreams?
  Q3 What is your dream job?
  Q4 Do you think you are an ambitious person?
  ```

- Visual direction: paper checklist / pencil sketch feeling.
- Only change UI visuals. Do not change layout, DOM structure, data structure, or behavior.
- Keep the existing P1 Library grid/layout intact.
- Frontend likely files:
  - `web/static/styles.css`
  - `web/static/corpus-takeaway.js`
  - `web/static/index.html`
  - `web/static/app.js`
- Bump relevant cache-busting query strings after edits if static JS/CSS cache strings are present.

Also finish the still-pending home-page polish if not done:

- The 1 -> 2 -> 3 training-loop arrows must connect cards cleanly.
- Arrows must be theme-adaptive.
- Number badges should look cleaner and less tacky.

## Refactoring Continuation

After the UI task is done, continue the existing refactoring plan.

Use repo context:

- `.trellis/tasks/`
- recent `refactor:` commits
- existing extraction work around speaking-service helpers

If that plan is complete, keep refactoring other large modules in safe, test-backed increments:

- `backend_django/apps/speaking/services.py`
- `web/static/app.js`
- `web/static/styles.css`

Keep refactoring continuously in practical increments. Do not ask the user what to do next.

## Verification

Before committing:

- For frontend edits:
  - `node --check web/static/app.js`
  - `node --check web/static/corpus-takeaway.js` if touched
  - `git diff --check`
- For backend refactors:
  - `python manage.py test apps.speaking`
  - Keep tests green.

## Git Rules

- Work on a branch.
- Commit as:
  - name: `Jasper-aa64`
  - email: `983640724@qq.com`
- Never use a company `psi.com` email.
- Never commit `.env`, `db.sqlite3`, or private credentials.
- Do not push unless already authorized.

