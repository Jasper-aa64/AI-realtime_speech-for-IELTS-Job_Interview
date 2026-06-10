# PRD: 上线 P2/P3 语料重构

## 背景

本轮目标是把已经验收的 P2/P3 语料重构整套上线到 `jasper/main`。当前本地 `main` 领先远端，且还有与本轮相关的未提交改动需要收口。

## 范围

- 收口 `backend_django/apps/speaking/services.py` 中的 bank P3 追问不截断逻辑。
- 收口 `web/static/app.js`、`web/static/corpus-takeaway.js`、`web/static/index.html`、`web/static/styles.css` 中的前端改动：
  - P3 报告编辑语料三路由。
  - P3 练习黄色提示按钮来源路由。
  - P3 启动面板单列全宽排版。
  - 已验收 UI 文案调整。
- 统一 bump 静态资源缓存串到 `20260607-p2p3-corpus-restructure`。
- 把本地资产目录加入 `.gitignore`，不提交：
  - `.claude/skills/ui-ux-pro-max/`
  - `.codex/skills/`
  - `软件构造/`
- 运行用户指定验证闸口，全绿后提交并推送 `jasper main`。

## 不做

- 不改需求。
- 不碰 `web/ielts_server.py`。
- 不提交 `db.sqlite3`、`.env`、key、`.venv-django`、build、WASM 产物、本地资产目录。
- 不碰 Windows 远端。
- 不把 fallback 伪装成 AI 成功。

## 验收

- `backend_django/apps/speaking/services.py` bank 输入不再被 `P3_MAIN_COUNT` 截断。
- 前端无半成品、调试残留、明显 dead commented code。
- `web/static/index.html` 的 `app.js`、`corpus-takeaway.js`、`styles.css` 缓存串一致。
- 指定验证命令全绿：
  - `.venv-django/bin/python backend_django/manage.py check`
  - `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
  - `node --check web/static/app.js`
  - `node --check web/static/corpus-takeaway.js`
  - `.venv-django/bin/python backend_django/manage.py test apps.speaking`
  - `.venv-django/bin/python backend_django/manage.py test`
  - `bash scripts/run_software_construction_deliverables_validation.sh`
  - `git diff --check`
- 提交后 `git show --stat HEAD` 不含红线文件。
- 推送 `git push jasper main` 成功。
