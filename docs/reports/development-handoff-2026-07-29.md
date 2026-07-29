# IELTS Studio 开发交接（2026-07-29）

下面的提示词可以直接交给新的 Codex 会话。它描述的是远端分支
`refactor/speaking-services-continue` 当前已经提交的代码和示例数据库。

## 可复制交接提示词

```text
你接手 IELTS Studio 项目。先不要凭感觉重写，也不要恢复旧文件覆盖当前代码。

仓库：
- GitHub: https://github.com/Jasper-aa64/AI_Project
- 分支: refactor/speaking-services-continue
- 拉取后先运行: git status -sb
- 当前提交包含 backend_django/db.sqlite3；这是用户明确要求版本化的示例账户数据库，
  不要因为它是运行数据而自动还原、忽略或删除。

开始前必须阅读：
1. AGENTS.md
2. docs/index.md
3. docs/ops/windows-startup-and-public-access.md
4. .trellis/spec/backend/p3-bank-practice-progress.md
5. .trellis/spec/frontend/index.md

当前已经落地的产品契约：

一、P3 固定题库采用“全题库统一周目”，不是每张题卡各自计算周目。
- 3–4 道固定追问：一次练完。
- 5 道：Q1 Q2 Q3 / Q4 Q5。
- 6 道：Q1 Q2 Q3 / Q4 Q5 Q6。
- 题卡使用无填充、左半填充、全部填充表示未完成、完成一半、全部完成。
- 题卡显示分组 tag，例如 Q1 Q2 Q3、Q4 Q5，不使用横杠区间。
- 当前待练分组高亮，其他分组变灰；全部完成后所有分组变灰。
- 点击已完成题卡时：只有一个分组就直接复练；多个分组才弹出 480px
  选择窗，让用户选择要复练的组。
- 复练照常生成报告，但 p3_bank_replay=true，不能增加本周目覆盖次数，
  也不能触发“本次完成后通关本周目”的提示。
- P3 次数以 SpeakingTrainingObservation 为持久来源，删除报告不重置次数。

二、P2 Brainstorm 当前筛选计数文案顺序：
「筛选」共 N 道 · P2 正文已填 M/N

三、深色第三主题的 P3 题卡、进度填充、分组 tag 已有单独可读配色。
鼠标悬停只增强边框，不覆盖题卡中间的进度填充。

关键实现位置：
- web/static/app.js:
  p3BankCardProgressState、p3BankRoundLabel、p3BankRoundChipsHtml、
  buildLocalP3BankPlanFromCard、openP3BankReplayPicker
- web/static/styles.css:
  p3-bank-picker-card、p3-bank-round-chip、p3-bank-replay-dialog
- backend_django/apps/speaking/corpus_services.py:
  _balanced_p3_bank_question_counts
- backend_django/apps/speaking/services.py:
  _attempt_records_training_observations，以及首次评分/重新生成报告的观察记录写入

验收命令：
node --check web/static/app.js
node tests/p2-brainstorm-body-status.test.js
node tests/p2-brainstorm-filter-motion.test.js
node tests/p3-bank-card-fill-progress.test.js
node tests/p3-bank-local-plan.test.js
node tests/p3-bank-cycle-progress.test.js
node tests/p3-bank-picker-cache.test.js
C:\Users\liangjunming\AppData\Local\Programs\Python\Python313\python.exe backend_django/manage.py test apps.speaking.tests.P3BankPracticeRoundTests apps.speaking.tests.QuestionBankApiTests
C:\Users\liangjunming\AppData\Local\Programs\Python\Python313\python.exe backend_django/manage.py check
git diff --check

Windows 服务边界：
- 常驻只有 NSSM 的 ielts-django 和 ielts-cloudflared。
- 普通前端改动只更新缓存号，不重启服务。
- 后端改动需要加载时只处理 Django，不要顺带重启 cloudflared；否则临时公网
  URL 会变化。
- 不要自行启动旧 watchdog、IELTS Stack Auto Start、LocalSystem worker。
- 只有用户明确要求时才启动交互用户 AI worker，并使用隐藏窗口方式。

工作方式：
- 工作区可能有用户自己的改动，永远先读 git status/diff，不能 reset 或覆盖。
- 修复前先写能复现问题的测试，改完跑相关完整回归。
- 不要把数据库当成可随意丢弃的临时文件。
```

## 本次发布内容

- P3 固定题库三态填充与全局周目展示。
- P3 分组 tag 的当前/已练状态。
- 已完成题卡的分组复练入口，以及复练不计数的前后端保护。
- P2 Brainstorm 筛选计数文案顺序。
- 对应前端回归、Django 回归和示例数据库快照。
