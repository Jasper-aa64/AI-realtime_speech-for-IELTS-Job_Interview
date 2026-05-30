# 实验2 实现：apps/ai 行为不变的设计模式重构

> 父设计任务：05-29-2（设计稿）。本任务执行其 Python 侧落地。
> 设计依据：`软件构造/实验2_设计文档.md`、`软件构造/重构总体架构.md`、`软件构造/实验2_类图.puml`。
> **核心约束：行为不变（behavior-preserving）。现有 `apps/ai/tests.py` 必须全绿，且不得修改测试。**

## 目标

把 `backend_django/apps/ai/provider_adapters.py`（714 行）从「if/elif + 重复 run() + 隐式降级」
重构为清晰的四模式结构，**对外行为与公开 API 完全不变**：
- **Strategy**：`AIProvider` 抽象接口（`run(task) -> ProviderRunResult`）。
- **Template Method**：`AiTaskTemplate` 基类，固定 run() 骨架 + `_build_prompt`/`_parse_payload`/`_on_failure` 钩子；
  `CodexWritingScoreAdapter`、`CodexSpeakingReportAdapter` 迁移为其子类。
- **Adapter**：抽 `CodexCliClient`（封装 `run_codex` + `extract_codex_json_events`，**消除隐藏双跑**）。
- **Chain of Responsibility**：`ProviderChain` 显式串联 `codex →(失败)→ fallback`；
  `FallbackProvider` 作为链尾，`outcome` 恒为 `FALLBACK` 带 metadata。

## 不可破坏的硬约束（安全网）

1. **不修改 `apps/ai/tests.py`**。测试是验收基准。
2. **保留所有被外部 import 的公开名字**（real class 或向后兼容别名）：
   `tests.py` 依赖：`AppliedProviderRunResult`、`CodexSpeakingReportAdapter`、`CodexWritingScoreAdapter`、
   `ProviderRunResult`、`apply_provider_run_result`、`run_claimed_ai_task`、`run_codex`、
   `select_provider_adapter`、`FallbackWritingScoreAdapter`、`MockSuccessWritingScoreAdapter`、
   `DEFAULT_FALLBACK_REASON`。
   `worker.py` 依赖：`run_claimed_ai_task`、`apply_provider_run_result`。
   —— 这些导入路径与签名必须继续可用。
3. **不改产品逻辑**：评分 prompt 内容、计费、AITask 状态机、orchestration 行为都不变。
4. **红线**：fallback 必带 metadata 明确标记，结构上不可能产出 `SUCCESS`；不加内容拦截器吞 AI 输出；
   follow-up/报告仍真调用 Codex（本任务不引入 HttpApiProvider，那是后续任务）。
5. **不动**：`apps/speaking/services.py`、`apps/writing/services.py`、前端、`web/ielts_server.py`、C++。
6. 不提交 git、不动 `db.sqlite3`。

## 范围内允许

- 拆分 `provider_adapters.py`：可新增 `apps/ai/providers.py`（策略类）、`apps/ai/codex_client.py`（Adaptee）、
  `apps/ai/provider_chain.py`（责任链），只要 `provider_adapters.py` 仍 re-export 上述公开名字保持兼容。
- 在 `provider_config.py` 内打通路由到链组装（不改其对外函数签名/行为）。

## 验收标准（Definition of Done）

- [ ] `python3 manage.py test apps.ai`（或等价）**全绿**，零测试改动。
- [ ] 四个模式在代码中真实成立（有 `AIProvider`/`AiTaskTemplate`/`CodexCliClient`/`ProviderChain`）。
- [ ] 写作评分与口语报告两条路径通过同一 `AiTaskTemplate` 骨架，消除重复。
- [ ] `run_codex` 的隐藏双跑被消除（json 失败不再静默再跑一次非 json）。
- [ ] 所有公开名字仍可从原路径 import。
- [ ] 在任务目录写 `CHANGES.md`：列出新增/移动的文件、保留的兼容别名、before/after 结构对比、测试结果。
