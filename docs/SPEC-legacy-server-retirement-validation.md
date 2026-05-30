# 规格：旧 server 退役验收断言脚本

> 给实现方（Codex）的需求文档。目标是给「旧 server 退役」补一条**可跑的验收断言**，
> 闭合 goal：旧 server 定格存档并退役 + Django 为唯一生产运行时 + 可验证闭环。
> **只接入既有验证脚本 + 总脚本。不改任何业务/服务/前端代码。**

## 背景（已是事实，无需改动，仅供断言依据）

- `web/ielts_server.py`（5418 行）头部已标 `DEPRECATED AND RETIRED`；默认启动被拦截：
  约第 220 行 `raise SystemExit(...)`，提示需 `IELTS_ALLOW_LEGACY_SERVER=1` 才能启动。
- `docs/LEGACY_SERVER_RETIREMENT.md` 已存在。
- `backend_django/`（`manage.py` + `config/urls.py`）是当前运行时；其中无 `ielts_server` 引用。
- 软件构造总验证脚本：`scripts/run_software_construction_deliverables_validation.sh`，
  顺序执行各实验验证脚本；任一步非 0 即整体失败。
- 旧 server 退役验证脚本：`scripts/validate_legacy_server_retirement.py` 已存在，
  目前包含 README、退役文档、冻结文件、Django import、Windows 启动器、Django URL surface、
  默认拒启这 7 条断言。

## 交付物（只此两项）

1. 复用 `scripts/validate_legacy_server_retirement.py`。
2. 在 `scripts/run_software_construction_deliverables_validation.sh` 的验证列表末尾
   追加一行接入该脚本。

## 脚本要实现的断言（全部通过才 exit 0，否则 exit 1）

每条断言失败要抛出清晰原因；全过打印 `PASS <check_name>`。

1. **旧 server 默认启动被拒**
   - 不设 `IELTS_ALLOW_LEGACY_SERVER`，运行 `web/ielts_server.py` 入口。
   - 期望：进程**非 0 退出**，且 stderr/stdout 含退役提示（如 `Refusing to start` 或 `retired`）。
   - ⚠️ 实现注意：macOS 无 GNU `timeout`。**不要用 `timeout`**。
     用 Python 子进程包装做超时，例如：
     `python3 -c "import subprocess,sys; r=subprocess.run([sys.executable,'web/ielts_server.py'],capture_output=True,text=True,timeout=15); ..."`，
     断言 `returncode != 0` 且输出含关键字。`timeout` 异常也算"未被正常拒绝"→ FAIL。

2. **带 escape flag 仍存在（定格存档，未被删除）**
   - 断言 `web/ielts_server.py` 文件存在且非空，且包含字符串 `IELTS_ALLOW_LEGACY_SERVER`。
   - 目的：证明是"退役+保留为参考"，不是"删文件"。

3. **生产代码无人依赖旧 server**
   - `grep -rn "ielts_server" backend_django/`（排除 `__pycache__`）应**无 import/调用**。
   - 允许注释/文档提及；若只想严格断言无 import，匹配 `import.*ielts_server` 或 `from.*ielts_server` 为空即可。

4. **Django 是可用运行时（冒烟，不起服务）**
   - 在 `backend_django/` 下跑 `python3 manage.py check`，期望退出码 0。
   - 不要真 `runserver`（会挂住）。`check` 足够证明 Django 配置可加载。
   - 若需要环境变量/settings，用项目现有默认；缺依赖导致 check 失败要如实 FAIL，不要吞掉。

5.（附加，轻量）**退役文档存在**
   - 断言 `docs/LEGACY_SERVER_RETIREMENT.md` 存在且非空。

## 接入总脚本

在 `scripts/run_software_construction_deliverables_validation.sh` 末尾 Experiment 5 验证之后追加：

```bash
python3 "${ROOT_DIR}/scripts/validate_legacy_server_retirement.py"
```

## 明确不做（边界，别扩展）

- 不改 `web/ielts_server.py`（不删、不动拦截逻辑）。
- 不改 `backend_django/` 任何业务/配置代码。
- 不改前端、`web/static/*`、不碰 C++/WASM。
- 不处理工作区现有 6 个无关脏文件（speaking/writing tests、db.sqlite3、ielts_agent_cli.py、styles.css、evaluate_writing_prompt_search.py）——那是别的开发线，不在本任务范围。
- 不新增依赖。

## 验收标准（用户验收用）

- [ ] `scripts/validate_legacy_server_retirement.py` 存在，单独运行 `python3 scripts/validate_legacy_server_retirement.py` → exit 0。
- [ ] 退役断言都在脚本内，且每条有清晰 PASS 输出或失败原因。
- [ ] `bash scripts/run_software_construction_deliverables_validation.sh` 整体仍 exit 0（新步骤已接入并通过）。
- [ ] 零业务/服务/前端代码改动（`git status` 只改总脚本 + 本任务文档）。
- [ ] 在任务目录留一份简短 CHANGES.md：新增了什么、退役断言跑出什么结果。
