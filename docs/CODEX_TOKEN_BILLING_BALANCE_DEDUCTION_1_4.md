# Codex Token 计费与余额扣减实施方案 v1.4

日期：2026-05-10

## 0. 结论

这件事不能做成“每次调用后减一个估算值”。正确做法是：

1. 先拿到每次 Codex 调用的**真实 usage**。
2. 用**版本化价格快照**把 token 变成 RMB。
3. 用**追加式账本**做 reservation / settlement / reconciliation。
4. 用**整数固定点**记账，禁止 float。

每个用户的初始余额建议直接发放 `5 RMB`，账本内部用更细的整数单位保存，展示层再按 `fen` 或 `RMB` 显示。

## 1. 研究结论

### 1.1 Codex 不会直接给你 RMB 账单

本地实测 `codex exec --json` 会返回类似：

```json
{"type":"turn.completed","usage":{"input_tokens":16540,"cached_input_tokens":13696,"output_tokens":557,"reasoning_output_tokens":516}}
```

这说明 Codex 能给出 token usage，但**不会天然返回可直接扣用户余额的 RMB 金额**。所以余额扣减必须由产品自己计算。

### 1.2 官方口径支持 token-based metering

OpenAI 官方文档已经把计费口径切到 token 维度：

- Responses API 的 `usage` 对象包含 `input_tokens`、`input_tokens_details.cached_tokens`、`output_tokens`、`output_tokens_details.reasoning_tokens` 和 `total_tokens`。
- 这些字段描述的是 token 消耗，不会直接给出 RMB。
- reasoning tokens 位于 output breakdown 中，不能再单独加一遍。
- Codex rate card 已经改成 token-based pricing，而不是 per-message。

这意味着：**我们可以，也应该，按 token 计费；但 RMB 价格必须来自我们自己的版本化快照，不是 CLI 自动给的。**

### 1.3 当前项目的不严谨点

现有实现里，以下地方不适合直接承担钱包扣费：

- `web/ielts_server.py` 的 `score_with_codex()` / `model_answer_with_codex()` 只拿文本结果，usage 被丢掉。
- `src/ielts/scorer.cpp` 的 `RunCodexExec()` / `RunOpenAIAPI()` 只保留输出文本，没有账务事件。
- `reports/attempts/` 是报告存储，不是账本；而且历史报告会被清理，不能拿来做资金记录。
- 目前没有稳定的 `user_id` 账务标识，不能用 `attempt_id`、`session_id` 或 `candidate` 冒充用户主键。
- 没有 reservation、settlement、idempotency、reconciliation，任何单点失败都会导致错账或漏账。

## 2. 计费目标

### 2.1 必须满足

- 每个用户初始余额：`5 RMB`。
- 扣费依据：**真实 token usage**，不是字数估算。
- 余额账本：**整数固定点**，禁止 float。
- 调用结算：**幂等**，同一个 call 只能结一次。
- 账务：**可审计、可回放、可对账**。

### 2.2 不做的事

- 不把 provider-native credits 直接当成产品余额。
- 不用 prompt 长度、字符数、人工规则去猜价格。
- 不把 billing 逻辑塞进 attempt JSON。
- 不允许“先扣个大概，后面再说”。

## 3. 账务模型

### 3.1 账本单位

建议内部使用 `μRMB`（1/1,000,000 RMB）作为账本单位。

- 用户展示余额仍然可以显示为 `RMB` / `fen`
- 账本内部保存为整数
- 5 RMB 初始赠金 = `5,000,000 μRMB`

如果只用 `fen`，token 级别的小额费用会积累舍入误差，不适合精确结算。

### 3.2 价格快照

价格必须版本化，不能硬编码在代码里。

建议结构：

- `snapshot_id`
- `model`
- `input_price_u_per_1m_tokens`
- `cached_input_price_u_per_1m_tokens`
- `output_price_u_per_1m_tokens`
- `reasoning_price_u_per_1m_tokens`（如果该适配器需要单独拆分）
- `effective_from`
- `effective_to`
- `source`（比如 `openai_codex_rate_card_2026_04_02`）
- `note`

这里的 `u` 表示 `μRMB`。

### 3.3 usage 归一化

必须先保存 raw usage，再做归一化。

推荐的规范化字段：

- `input_tokens_total`
- `cached_input_tokens`
- `output_tokens`
- `reasoning_output_tokens`
- `provider`
- `model`
- `raw_usage_json`
- `semantics_version`

建议统一规则：

- `billable_uncached_input_tokens = input_tokens_total - cached_input_tokens`
- `billable_cached_input_tokens = cached_input_tokens`
- `billable_output_tokens = output_tokens`
- `reasoning_output_tokens` 只做诊断和 reserve sizing，不单独收费

关键点是：**不要在两个层级重复计算 reasoning tokens。**

### 3.4 精确计费公式

单次调用的精确计费建议用整数分子 / 分母累计：

```text
charge_numerator_u =
  billable_uncached_input_tokens * input_price_u_per_1m_tokens +
  cached_input_tokens * cached_input_price_u_per_1m_tokens +
  output_tokens * output_price_u_per_1m_tokens

settled_u = floor((carry_numerator_u + charge_numerator_u) / 1_000_000)
carry_numerator_u = (carry_numerator_u + charge_numerator_u) % 1_000_000
```

解释：

- `charge_numerator_u` 的单位是 `μRMB * token`
- 分母 `1_000_000` 对应 “per 1M tokens”
- `carry_numerator_u` 用来保存小数部分，避免每次调用都舍入损失

这样可以做到：

- 单次不丢精度
- 多次调用后累计也不漂移
- 账本仍然是整数

### 3.5 如果 provider 价格不是 RMB，先做 FX 快照

如果官方 rate card 或内部采购价不是 RMB，不能直接把它写进账本。应该先建立一个独立的 FX 快照，再生成人民币结算价。

建议字段：

- `fx_snapshot_id`
- `from_currency`
- `to_currency`
- `fx_rate`
- `fx_source`
- `effective_from`
- `effective_to`
- `settlement_policy`

结算价生成规则：

```text
settlement_price_rmb = provider_price * fx_rate + business_markup
```

如果产品决定直接维护 RMB 价格表，也要把这个价格表版本化，不能把 rate card 数值硬编码到代码里。

## 4. 调用链路设计

### 4.1 先 reserve，再执行，再 settle

每次 Codex 调用都必须经过同一条链路：

1. 生成 `call_id`
2. 计算最坏情况 reserve
3. 锁定用户余额
4. 执行 Codex
5. 读取 raw JSONL / usage，并用 `--output-last-message` 单独保留最终助手文本
6. 结算实际金额
7. 释放多余 reserve

### 4.2 reserve 的算法

reserve 不能拍脑袋，必须基于：

- prompt 的**精确 token 预估**
- 当前请求的 `max_output_tokens`
- 当前 price snapshot
- 一个明确的 safety margin

如果当前 adapter 没有稳定的 exact tokenizer，就需要先补 tokenization 依赖；没有这个能力，reserve 只能保守，不能精确。

推荐公式：

```text
reserve_u =
  ceil((prompt_upper_bound_tokens * input_price_u_per_1m_tokens +
        max_output_tokens * output_price_u_per_1m_tokens) / 1_000_000)
  + safety_margin_u
```

### 4.3 结算状态机

建议状态：

- `initiated`
- `reserved`
- `usage_captured`
- `settled`
- `released`
- `pending_reconciliation`
- `failed_no_usage`

原则：

- 有 authoritative usage，就按 usage 结算
- 没有 authoritative usage，就不要猜
- 结算必须幂等

## 5. 数据结构

### 5.1 建议使用独立 SQLite 账本

当前项目是文件型存储，但钱包需要事务、唯一约束和并发控制，所以建议单独加一个账本库，比如：

- `reports/billing/billing.sqlite3`

并开启 WAL。

不要把账务永久写进 `reports/attempts/`。

### 5.2 表结构建议

#### `users`

- `user_id` PK
- `display_name`
- `balance_u`
- `reserved_u`
- `status`
- `created_at`
- `updated_at`

#### `wallet_ledger_entries`

- `entry_id` PK
- `user_id`
- `call_id`
- `entry_type`：`grant | reserve | settle | release | adjust | refund`
- `amount_u`
- `snapshot_id`
- `usage_id`
- `idempotency_key`
- `metadata_json`
- `created_at`

#### `codex_usage_events`

- `usage_id` PK
- `call_id` UNIQUE
- `provider`
- `model`
- `raw_jsonl_path`
- `input_tokens`
- `cached_input_tokens`
- `output_tokens`
- `reasoning_output_tokens`
- `semantics_version`
- `captured_at`

#### `price_snapshots`

- `snapshot_id` PK
- `model`
- `input_price_u_per_1m_tokens`
- `cached_input_price_u_per_1m_tokens`
- `output_price_u_per_1m_tokens`
- `reasoning_price_u_per_1m_tokens`
- `effective_from`
- `effective_to`
- `source`

#### `wallet_reservations`

- `reservation_id` PK
- `user_id`
- `call_id` UNIQUE
- `reserved_u`
- `status`
- `expires_at`
- `created_at`
- `released_at`

### 5.3 用户身份

不能把 `candidate` 当成 billing 主键。

必须引入稳定的 `user_id`：

- 真实产品：登录用户 / 账号体系
- 本地单机：可以先用一个默认用户，但数据模型仍然要按多用户设计

## 6. 现有代码怎么改

### 6.1 Python Web 路径

重点改：

- `web/ielts_server.py::score_with_codex()`
- `web/ielts_server.py::model_answer_with_codex()`

改造目标：

- 改成 `codex exec --json`
- 逐行保存 raw event stream
- 提取 `turn.completed.usage`
- 如果还需要最终自然语言答案，配合 `--output-last-message`
- 把 `call_id`、`usage_id`、`snapshot_id` 一起写入账本

### 6.2 C++ 路径

重点改：

- `src/ielts/scorer.cpp::RunCodexExec()`
- `src/ielts/scorer.cpp::RunOpenAIAPI()`
- `include/ielts/scorer.h`

改造目标：

- 返回值不能再只是 `std::string`
- 至少要返回：
  - assistant text
  - raw jsonl path / raw stdout
  - parsed usage
  - exit code
  - call_id

### 6.3 配置

建议新增 `billing` 配置块到 `config/default_config.json`，包含：

- 初始赠金
- 价格快照 id
- reserve 安全边际
- 是否允许负余额
- 是否启用 shadow mode

### 6.4 前端

`web/static/app.js` 需要补：

- 当前余额
- 本次调用预扣金额
- 本次调用实扣金额
- 失败 / 待对账状态
- 最近账本流水

## 7. 失败与对账

### 7.1 没有 usage

如果 Codex 调用失败，但没有拿到 authoritative usage：

- 不要猜 cost
- 不要按 prompt 长度补扣
- 标记为 `pending_reconciliation`
- 后台重试恢复 raw event stream

### 7.2 部分成功

如果模型已经消耗 token，但最终输出失败：

- 只按已捕获 usage 结算
- 仍然要落账
- 不能因为没有最终答案就免单

### 7.3 幂等

同一个 `call_id` 只能结算一次。

必须有唯一约束：

- `(provider, call_id)`
- `(user_id, call_id, entry_type)`

避免重复提交、重试、网络抖动导致二次扣费。

### 7.4 对账

每天跑一次 reconciliation：

- 比对 raw usage event
- 比对 ledger entry
- 比对 attempt/report 归档
- 检查 reservation 是否泄漏
- 检查 pending 状态是否超时

## 8. 落地顺序

### Phase 1：只采集，不扣费

先把 raw usage 全量落盘，不做余额变化。

### Phase 2：影子计费

后台并行计算应扣金额，但不真正扣账，验证价格表和语义映射。

### Phase 3：预扣 + 结算

只对小流量用户开启 reservation / settlement。

### Phase 4：全量启用

再放开到所有用户，并保留回放和人工审核入口。

## 9. 测试计划

至少要补这些测试：

- 初始余额 `5 RMB` 是否准确入账
- 同一 `call_id` 重放不会重复扣费
- `cached_input_tokens` 走便宜价
- `reasoning_output_tokens` 不重复计费
- reserve 足够时能自动释放剩余额度
- usage 缺失时不会盲扣
- 并发调用不会超卖余额
- price snapshot 切换后历史账单仍可回放

## 10. 这版方案的核心边界

这不是一个“给用户发个余额数字”的前端功能，而是一个**账本系统**。

如果没有以下四项，扣费就不算完成：

1. authoritative usage
2. versioned price snapshot
3. append-only ledger
4. idempotent settlement

## 11. 参考来源

- [OpenAI Responses API: retrieve / usage](https://platform.openai.com/docs/api-reference/responses/retrieve)
- [OpenAI Reasoning guide](https://platform.openai.com/docs/guides/reasoning)
- [OpenAI Codex rate card](https://help.openai.com/en/articles/20001106-codex-rate-card)
- 本地实测：`codex exec --json` 返回 `turn.completed.usage`
