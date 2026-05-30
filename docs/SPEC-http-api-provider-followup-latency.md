# Goal 规格：真考官式追问做成流畅体验（HTTP API 直连 + 追问提速）

> 阶段性大 goal。给实现方（Codex）。用户负责 review + 验收；本规格定目标、边界、验收、红线。
> 一句话：把后端 AI 从 **Codex CLI 子进程冷启** 迁到 **OpenAI 兼容 HTTP API 流式直连**，
> 让 P3/P1 追问延迟从十几秒压到秒级，兑现实验2 设计的 `HttpApiProvider`。

## 0. 为什么做这个（背景，不需改动，仅供理解）

- 当前后端 **100% 靠 codex CLI 子进程**：`apps/speaking/services.py` 的 `run_codex` 和
  `quick_follow_up_runner` 每次都 `subprocess.run([codex, "exec", ...])`，冷启 + reasoning，十几秒起步。
- `apps/ai/provider_config.py` 已埋好 `openai`/`claude` 的开关与 secret env 名，但
  **`HttpApiProvider` 从未实现**（实验2 只设计未落地，`provider_config`/`tests` 里有名字、无实现）。
- 用户核心产品价值 = **真考官式追问**（P3 考官贴着学生答案追问）。其瓶颈不是追问逻辑（已有
  `quick_follow_up_runner` / `_generate_p3_dynamic_follow_up`），而是 **LLM 响应延迟**。
- 用户手上有 **OpenAI 兼容端点**（多家）。

## 1. Goal 定义（验收绑追问体验，不只是 benchmark）

把"追问"这条用户实时等待的路径，从 codex CLI 切到 HTTP API 流式直连，体验上从
"问完等十几秒" 变成 "1–3 秒内出追问"。

## 2. 范围（按风险从低到高，建议分步提交）

### 2.1 实现 `HttpApiProvider`（provider 可配，不写死任何一家）
- 新增 OpenAI 兼容 HTTP 客户端（用 `httpx` 或 `requests`；流式优先 `stream=True`）。
- **全部走环境变量，代码零硬编码**：
  - `AI_HTTP_BASE_URL`（如 `https://api.openai.com/v1` 或国内兼容端点）
  - `AI_HTTP_API_KEY`（**只读环境变量，绝不进代码/日志/git**）
  - `AI_HTTP_MODEL`（如 `gpt-4o-mini` 或兼容模型名）
- 实现成 `AIProvider` 策略（对齐实验2 `软件构造/实验2_设计文档.md` 的 Strategy/Adapter）。
- 打通 `provider_config.resolve_provider_route()`：当 `AI_PROVIDER_ENABLE_OPENAI`（或等价开关）
  开启时，路由到 `HttpApiProvider`。

### 2.2 把追问路径切到 HTTP（核心提速点）
- `quick_follow_up_runner` 增加 HTTP 路径：优先走 `HttpApiProvider`，**失败再 fallback 到 codex CLI**。
- 关闭追问的 reasoning 开销（小快模型 + 无 reasoning），追问是"接一句话"的轻任务。
- 流式：能流式就流式（首 token 尽快返回）；非流式也要比 CLI 冷启快得多。

### 2.3 责任链/降级（红线，对齐实验2）
- 链：`HttpApiProvider →(失败/超时)→ CodexProvider →(失败)→ 明确标记 fallback`。
- **fallback 必带 metadata 明确标记**，结构上不可能冒充"AI 成功"。不加内容拦截器吞输出。

### 2.4 延迟对比数据（验收证据）
- 一个小脚本/测试，量同一批追问 prompt 在 **codex CLI vs HTTP API** 的耗时（P50/P95、失败率）。
- 不要求严谨 benchmark，但要能在验收报告里给出"提速前后"对比数字。

## 3. 明确不做（边界）

- **不做 realtime gateway / 边说边出字**（那是 backlog 的独立大工程，B 层"能打断"不在本 goal）。
- 不改前端 UI / `app.js` 产品逻辑（追问 API 提速对前端透明；若前端需配合流式渲染，单列后续）。
- 不动 WASM / C++ 线（已闭环）。
- 不动 `web/ielts_server.py`（已退役）。
- 不重写追问的 prompt 内容/题库逻辑——只换"调用通道"，不换"问什么"。
- **不碰工作区现有业务 WIP 脏文件**：`app.js`/`index.html`/`styles.css` 其余改动、
  `speaking/writing tests`、`db.sqlite3`、`ielts_agent_cli.py`、`evaluate_writing_prompt_search.py`。
  继续局部 staging。
- 不提交任何 API key；key 只走环境变量。

## 4. 红线

- follow-up / 报告必须真调用 AI；fallback 必带 metadata 标记，不得伪装 AI 成功。
- API key 绝不进代码、日志、git、错误信息。
- 现有测试必须全绿，且不得为了通过而改测试逻辑。
- provider 不写死任何一家——`base_url`/`key`/`model` 全可配。

## 5. 验收标准（用户验收用）

- [ ] `HttpApiProvider` 实现，`base_url/key/model` 全走环境变量，无硬编码。
- [ ] 追问路径（`quick_follow_up_runner`）优先走 HTTP，失败 fallback codex，再失败明确标记 fallback。
- [ ] 提供延迟对比：codex CLI vs HTTP API 的追问耗时（数字写进 CHANGES）。
- [ ] 责任链降级可演示：HTTP 失败 → codex → fallback(带 metadata)，无伪造成功。
- [ ] 全量 `python3 manage.py test` 全绿，测试无逻辑改动。
- [ ] `python3 manage.py check` 通过。
- [ ] 零业务 WIP 脏文件被夹带；分步提交（client / provider / 追问切换 / 对比脚本 各自 commit）。
- [ ] CHANGES.md：实现了什么、追问提速前后数字、降级链如何验证、保留的兼容路径。

## 6. 与实验作业的关系

本 goal 兑现 `软件构造/实验2_设计文档.md` 里 `HttpApiProvider`（Strategy/Adapter/责任链）的
落地——作业设计 → 产品实现在此合流。完成后实验2 的"可运行重构"从写作评分扩展到追问链路。
