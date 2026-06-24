# IELTS Web Headless Long Run Audit

日期：2026-05-12  
范围：本地 IELTS Speaking Web 产品，重点检查前端交互、报告页、目标分回答、AI 辅导、钱包/训练入口、移动端适配和后端高风险路径。

## 结论

这轮 headless 巡检没有发现 P0 级阻断问题。当前版本可以启动，主导航可点击，History 可以选择历史报告，报告详情会渲染卡片式题目报告，目标分回答和 AI 辅导区域存在，移动端 390px 视口没有横向溢出。

但它还不是“工业级完成态”。下一轮最值得继续精进的是：

- 报告页需要更清楚展示 AI 生成来源、usage、fallback 状态和发音评估可信度。
- Settings 里仍然展示弱题训练/复习队列，和“复习部分不在界面显示”的产品边界不完全一致。
- 钱包金额仍使用 6 位小数，视觉上不像面向普通用户的 RMB 余额。
- 前端和后端单文件规模已经偏大，继续加功能会明显增加回归风险。
- 缺少真正自动化的浏览器端到端测试，目前 headless 巡检靠脚本手动执行。

## 已验证项目

### 基础检查

通过：

```bash
python -m py_compile web/ielts_server.py tests/test_ielts_web_server.py
node --check web/static/app.js
python -m unittest tests.test_ielts_web_server
```

结果：

- Python 编译通过。
- 前端 JS 语法检查通过。
- 单元测试 37 个全部通过。
- `data/ielts/**/*.json` JSON 解析检查通过。

### Headless UI 巡检

启动本地服务：

```bash
python web/ielts_server.py --host 127.0.0.1 --port 8765 --reports-dir <temp-dir>
```

浏览器巡检结果：

- `Mock / P1 / P2 / P3 / History / Settings` 六个左侧导航都能点击。
- History 页面顶部报告选择 rail 存在。
- 空 History 状态不报错。
- 生成一条临时 P1 报告后，History 可以选中报告并渲染详情。
- 报告详情渲染为卡片结构，不再是拥挤表格。
- 每题卡片包含：
  - `我的回答`
  - `目标 7.5 分回答`
  - `AI 辅导`
- `target_band` 从前端传到后端评分接口。
- 390px 移动端模拟下无横向溢出。
- 页面可见文本没有发现连续问号占位、英文半成品标题、Unicode replacement 字符等异常文案。

### API 巡检

通过：

- `GET /api/history`
- `GET /api/billing/wallet`
- `GET /api/training/weak-items`
- `GET /api/training/replay-queue`
- `GET /api/question-bank/summary`

观察：

- `/api/settings` 不存在。当前 Settings 页面是前端分别请求钱包、弱题、复习队列等接口。这不是阻断 bug，但会让页面状态更分散。
- 临时 P1 报告完整完成后，`/api/history` 能返回报告项。

## 重点发现

### P0 阻断问题

暂无。

当前没有发现页面卡死、导航不可点、History 完全无法进入、JS 语法错误、后端无法启动这类阻断问题。

### P1 建议优先处理

#### 1. 报告页的 AI 来源透明度还不够

后端已经有 `billing_usage`、`scoring_backend`、`target_band`、`pronunciation.status`、`personalized_coaching` 等字段基础，但前端报告详情还没有把这些信息完整地结构化展示出来。

建议下一批增加一个“生成信息”区域：

- 评分来源：`codex-cli` / fallback。
- 中文解释来源：`codex-cli` / fallback。
- 目标分回答来源：`codex-cli` / fallback。
- ASR 清理来源：`codex-cli` / fallback。
- pronunciation 是否来自真实音频分析，还是不可评估。
- usage/call_id/token/扣费状态。

这对用户信任很重要。现在用户看到 AI 辅导，但很难判断“这是本机 Codex 真生成的，还是 fallback 模板”。

#### 2. Settings 内容边界需要再收紧

用户之前明确说过：复习部分只影响低于平均分题目的复现次数，不在界面显示。

当前 `Settings` 里仍然加载并展示：

- 弱题训练
- 复习队列

建议：

- Settings 只保留模型、TTS、候选人、开发配置和计费配置状态。
- 弱题/复习数据继续作为后端策略存在，但默认不在 UI 中暴露。
- 如果要给调试入口，应折叠到开发模式，不面向普通用户显示。

#### 3. 钱包金额展示需要产品化

当前前端仍显示：

```text
余额 ¥5.000000 · 预留 ¥0.000000
```

建议 UI 显示改为：

```text
余额 ¥5.00
预留 ¥0.00
```

流水明细中可以保留更精确的内部单位，但默认用户界面不应展示 6 位小数。

#### 4. P1 turn 数动态变 11 需要产品解释

临时 P1 smoke 中，初始 P1 attempt 有 10 个 turn，完成中途插入了 identity follow-up，最终报告渲染 11 张卡片。

这可能是设计上刻意模拟考官追问，但 UI 没有解释“追问题”为什么多出来。建议：

- 在报告卡片中更明确标记 `Follow-up` 的来源。
- 在练习流程里把追问题计数与主问题计数区分开。
- History 摘要中不要只写 `10 questions` 或 `11 questions`，可以写 `10 main + 1 follow-up`。

### P2 可排队优化

#### 1. 前端仍是单文件大模块

当前规模：

- `web/static/app.js`：1149 行。
- `web/static/styles.css`：1593 行。

建议按不引入大型框架的前提拆分：

- `api.js`
- `state.js`
- `practice.js`
- `reports.js`
- `wallet.js`
- `settings.js`
- `ui.js`

CSS 也可以先拆 token 和组件：

- `tokens.css`
- `layout.css`
- `practice.css`
- `reports.css`
- `settings.css`

#### 2. 后端服务文件过大

当前 `web/ielts_server.py` 约 3229 行，包含：

- billing
- training
- question bank
- scoring
- codex CLI
- TTS
- HTTP handler

建议先按纯 Python 模块拆，不改协议：

- `billing.py`
- `training.py`
- `scoring.py`
- `codex_backend.py`
- `tts.py`
- `reports.py`
- `server.py`

这样后续继续增强 AI scoring / coaching 时，风险会小很多。

#### 3. 缺少浏览器端到端测试

现在有不错的后端单元测试，但没有稳定的浏览器测试。建议补一个最小 headless smoke：

- 启动临时 reports dir。
- 打开首页。
- 点击 Mock/P1/P2/P3/History/Settings。
- 创建一条测试报告。
- 进入 History 并断言报告卡片出现。
- 检查移动端无横向溢出。
- 检查页面文本没有连续问号占位、Unicode replacement 字符或半英文占位文案。

可以先不引入复杂测试框架，用 Chrome DevTools Protocol 脚本也够用。

#### 4. 文档编码需要纳入巡检

本次读取旧文档时，部分终端输出出现过乱码现象。按 UTF-8 读取文件后内容正常，但 Windows PowerShell 默认编码容易误导排查。

建议：

- 所有报告文档统一 UTF-8。
- 加一个简单脚本检查 `docs/*.md` 是否包含 Unicode replacement 字符、连续问号占位或常见 mojibake 片段。
- 终端输出中文时设置 `PYTHONIOENCODING=utf-8`。

## 建议下一批实现顺序

1. 先修 Settings 边界和钱包金额展示。这是小改动，用户感知强，风险低。
2. 报告详情增加“生成信息 / 可信度 / usage”区域，让 AI 生成链路透明。
3. 把 History 摘要和报告详情里的 follow-up 计数讲清楚。
4. 增加 headless smoke 测试脚本，固定住“导航可点、报告可选、移动端不溢出、无乱码”。
5. 再做 `app.js` / `ielts_server.py` 模块拆分，避免继续在大文件上堆复杂功能。

## 本轮未改动的产品代码

本轮任务主要是 headless long run audit。除生成本报告外，不应包含产品代码改动。

## 临时测试说明

为验证 History 报告渲染，本轮用临时 reports 目录生成过一条 P1 测试报告。该数据只存在临时目录，不写入默认用户报告目录。
