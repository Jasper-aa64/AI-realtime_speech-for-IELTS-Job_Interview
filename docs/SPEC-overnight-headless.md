# Goal 规格：夜间 headless 自主推进（无人值守，不依赖用户 / 不依赖 key）

> 给实现方（Codex headless）。用户睡觉，全程无人验收。
> **铁律：只做能自验对错、不需要人点浏览器、不需要 ASR/HTTP key 的活。**
> 任何需要真实端点、真实浏览器、用户决策的事 → 停下，写进 BLOCKED 清单，跳过，做下一项。

## 0. 最高安全铁律（无人值守，违反即停）

1. **每一刀完成的唯一标准 = 全量 `python3 manage.py test` 全绿（当前基线 270）+ `manage.py check` 通过 + 涉及前端则 `node --check` 通过。** 任一不过 → `git restore` 撤回这刀，记进 BLOCKED，跳到下一项。**绝不留红提交。**
2. **绝不碰真实 ASR / HTTP API key、绝不真连 openspeech / 真 LLM 端点。** 只用 fake websocket / mock / 单测。需要真实端点的 → 写进 BLOCKED，不做。
3. **绝不要求浏览器人工点击验收。** 首字延迟、边说边出字这类需要真人说话/看屏的 → 写进 BLOCKED，不做。
4. **baseline 不破**：现有同步栈、批处理录音、所有现有 API/页面行为不变。realtime 全是默认关的叠加层。
5. **一刀一独立 commit**，commit message 清晰。**绝不夹带** `db.sqlite3` 和与本刀无关的 WIP 脏文件。
6. **不 push、不改 git 配置、不 reset 已有提交。**

## 1. 开工前：先把工作区现有 WIP 收拾干净

当前脏文件（2.3 逻辑层进行中 + 其他 WIP）：`consumers.py / corpus_services.py /
test_asgi_channels.py / tests.py / app.js / index.html / docs spec / db.sqlite3`。

- 先判断哪些属于**正在做的 2.3 逻辑层**（consumers.py / test_asgi_channels.py / 前端转写渲染）→
  完成它（见任务 A），独立提交。
- 其余无关 WIP（corpus_services.py / tests.py 等若与 2.3 无关）→ **保持不动，不提交、不撤销**，
  只是别夹带进 commit。
- `db.sqlite3` 永远不提交。

## 2. 任务队列（按顺序做，每项独立可跑、失败可跳）

### 任务 A：完成 Phase 2.3 ASR 串联——**仅逻辑层（fake websocket）**
- `/ws/realtime/pcm/` consumer 收 PCM → 喂 `stream_pcm_chunks()` → `interim/final` 转写事件
  实时 WS 回前端 → 前端边说边把转写滚动显示（DOM 渲染逻辑写好）。
- **用 fake websocket 全覆盖测试**：多次 interim + final + done + 中途断开降级。
- ASR key/端点全走环境变量；未配 key 时优雅提示/回落，不崩。
- **CHANGES 必须明确写**：「逻辑层已测，真实 openspeech 端点待用户配 key 验收」——不得声称"边说边出字已完成"。
- 真实端点验收 = BLOCKED（留给用户）。

### 任务 B：app.js 继续模块化（纯自验，安全）
- 当前 ~8356 行。继续按低风险块抽模块（如 report 渲染、speaking runtime 视图层、account 视图）。
- 每刀：抽一个内聚块 → `app.js` 留 facade → Django 静态路由补新模块 → index.html bump 版本 →
  `node --check` 双文件 + `manage.py check` + 该模块相关单测/已有测试全绿 → 独立 commit。
- **一刀一提交，每刀报行数**。不改任何产品行为/UI，纯搬运。

### 任务 C：speaking/services.py 继续拆（纯自验，安全）
- 当前 ~4386 行。继续抽纯函数/低副作用块（参考已拆的 scoring/report/text_utils 模式）。
- facade re-export 保住所有 `from apps.speaking.services import X` 调用方。
- 每刀全量 test 全绿 + 独立 commit。

### 任务 D（有余力才做）：补测试覆盖
- 给 realtime ASR 逻辑层、streaming follow-up、provider 责任链补边界用例（fake/mock）。
- 只增测试，不改被测逻辑。每加一批跑全量绿 + 提交。

## 3. 不做（BLOCKED 清单，留给用户）

- 真实 openspeech ASR 端点验收（需 key）
- 真实 HTTP LLM 端点 benchmark（需 key）
- 浏览器首字延迟实测 / 边说边出字真人验（需真人）
- 2.4 串追问、2.5 首字实测里**任何需要真实端点或真人的部分**（逻辑层可做，真实验收 BLOCKED）
- 发音评测、能打断全双工（backlog，未设计）
- 任何 git push / 部署

## 4. 早晨交付（给用户的晨报）

在 `docs/OVERNIGHT-REPORT.md` 写：
- 完成了哪几刀（每刀 commit hash + 一句话 + 关键数字如行数/测试数）
- 全程测试基线变化（起 270 → 终 X，必须只增不减）
- **BLOCKED 清单**：哪些卡在 key/浏览器/用户决策，等用户回来做什么
- 工作区最终状态（应只剩本就无关的 WIP + db.sqlite3）
- 如果某刀失败撤回了，如实记录失败原因

## 5. 优先级与停止条件

- 顺序：A（收尾在做的 2.3 逻辑层）→ B（app.js 拆，可多刀）→ C（speaking 拆，可多刀）→ D（补测试）。
- **任何一刀连续两次无法让全量测试转绿 → 撤回该刀、记 BLOCKED、跳到下一项**，不要在一个坑里耗整夜。
- B/C 可以一直做到天亮（大文件够拆很多刀），每刀独立提交，安全增量。
