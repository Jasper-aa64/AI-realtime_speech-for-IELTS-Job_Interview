# Goal 规格：阶段性收口（立存档点 + 出重构完成度报告）

> 阶段性大 goal。给实现方（Codex）。用户负责 review + 验收。
> 目的：在继续切 app.js 之前，**立一个存档点**——把"重构到哪了"白纸黑字定下来，
> 让进展可回溯、可向用户证明完成度。
> **不开新功能、不进攻新大文件、本 goal 期间暂停 app.js 切分。**

## 为什么现在收口（指挥说明）

app.js 模块化方向正确（已抽 shared-ui / view-router / writing-image-preload 等），但
8776 行还要切很多刀。继续无存档点地往前切，会重演"MVP+补丁"的老毛病——不知道还剩多少、
进展无法量化。先立存档点，再继续切。

## 现状（已核实，2026-05-30）

- 工作区基本 clean：仅 `backend_django/db.sqlite3`（M，C 类不提交项）。**上一轮 10 个业务 WIP
  脏文件 Codex 已自行分线处理完毕**——脏文件分线任务**基本完成，无需再做**。
- 前端已拆出模块：`api-client.js`(68) `appearance.js`(94) `shared-ui.js`(193)
  `view-router.js`(151) `writing-image-preload.js`(141)；`app.js` 仍 8776 行。
- 后端已拆出模块：speaking 分出 `corpus/report/scoring/text_utils/audio/tts` 六个；
  `speaking/services.py` 4433→4139；`writing/services.py` 993→605。

## 任务（只此一项）：出《重构完成度报告》

新增 `软件构造/重构完成度报告.md`，写清"重构到哪了、还剩什么、怎么量化"。

**已完成（每项带证据 commit / 数字）**
- apps/ai provider 结构化重构（实验2：Strategy/Adapter/责任链/Template）
- C++ audio_core 纯核抽取 + libfvad 开源 VAD + WASM 默认启用（feature flag→默认 on，含降级）
- HttpApiProvider 追问提速：真实端点验收通过（HTTP 3/3 成功 P50≈4.66s、单次最好 1.46s；
  对照轮 Codex CLI 失败而 HTTP 成功——秒级达标 + 可靠性质变）
- 旧 server 退役：标记 + 拦截 + 文档 + 验证脚本 + 已接入总验证脚本（完整闭环）
- writing/services.py 拆分（993→605）
- speaking/services.py 拆分（4433→4139，六模块）
- 前端 app.js 模块化启动（已抽 5 个模块，app.js→8776）

**剩余技术债（明确列出 + 按性价比排序）**
- `web/static/app.js` 仍 8776 行（单文件 SPA，模块化进行中，下阶段继续切：
  下一刀=写作 prompt picker 渲染/筛选）
- `speaking/services.py` 仍 4139 行（runtime/TTS/Codex runtime 未拆）
- 追问延迟 4.66s→稳定 1-3s（调优项：流式首字 / 换更快模型，非重构）
- realtime gateway「能打断」（backlog，未启动）
- 发音评测（backlog，待查语音服务是否支持音素级评分）

**基线数字表**（本轮快照，供下阶段量化进展对比）
| 文件/模块 | 当前行数 | 起始 | 备注 |
|---|---|---|---|
| app.js | 8776 | ~8905 | 模块化进行中 |
| speaking/services.py | 4139 | 4433 | 六模块已拆 |
| writing/services.py | 605 | 993 | report_services 已拆 |
| 前端已拆模块 | 5 个 | 0 | api-client/appearance/shared-ui/view-router/writing-image-preload |

## 验收标准（用户验收用）

- [ ] `软件构造/重构完成度报告.md` 存在：已完成项带证据、剩余债务明确且排序、含基线数字表。
- [ ] 报告如实标注"追问延迟 4.66s 待优化"，不粉饰。
- [ ] 全量 `python3 manage.py test` 仍全绿；`manage.py check` 通过（回归确认，未引入破坏）。
- [ ] `bash scripts/run_software_construction_deliverables_validation.sh` 整体 exit 0（退役已接入，回归）。
- [ ] 提交：`docs: add refactoring completion report`（不夹带 db.sqlite3 等噪音）。

## 明确不做（边界）

- 本 goal 期间**暂停 app.js 切分**（存档点立完再继续）。
- 不进攻 speaking/services.py 新拆分。
- 不开 realtime / 发音评测 / 延迟调优任何代码。
- 不动 db.sqlite3。
