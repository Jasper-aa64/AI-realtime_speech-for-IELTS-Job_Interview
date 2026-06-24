# Docs 导航

这是 `docs/` 的总地图(Map, not Manual)。每个条目一句话说明用途,详情点进去看。
根目录不再堆散文件;新文档按下面的分类放进对应子目录。

> 给 agent 看的规范 / 设计 / 计划文档统一在 [`superpowers/`](superpowers/index.md)。

## ops/ — 启动 · 部署 · 公网

| 文档 | 用途 |
| --- | --- |
| [windows-startup-and-public-access.md](ops/windows-startup-and-public-access.md) | **启动/重启/公网/502 必读**:Django + AI worker 启动路径、NSSM 服务、计划任务、Cloudflare 隧道、502 排查清单 |
| [开机启动清单.md](ops/开机启动清单.md) | 开机后手动核对清单 |
| [windows-deployment-handoff.md](ops/windows-deployment-handoff.md) | Windows 部署交接说明 |
| [legacy-server-retirement.md](ops/legacy-server-retirement.md) | 旧 `web/ielts_server.py` 退役约束与允许调试的边界 |

## product/ — 产品 · 业务

| 文档 | 用途 |
| --- | --- |
| [functional-overview.md](product/functional-overview.md) | 产品功能总览 |
| [business-analysis-handoff-2026-06-14.md](product/business-analysis-handoff-2026-06-14.md) | 业务分析交接(2026-06-14) |

## reports/ — 报告 · 审计 · review

| 文档 | 用途 |
| --- | --- |
| [overnight-report.md](reports/overnight-report.md) | 隔夜 headless 运行报告 |
| [headless-long-run-audit-2026-05-12.md](reports/headless-long-run-audit-2026-05-12.md) | headless 长跑审计(2026-05-12) |
| [scoring-calibration-change-report-2026-05-12.md](reports/scoring-calibration-change-report-2026-05-12.md) | 评分校准变更报告(2026-05-12) |
| [stage-consolidation-changes.md](reports/stage-consolidation-changes.md) | stage 收口改动记录 |
| [speaking-2026-may-august-bank-review.md](reports/speaking-2026-may-august-bank-review.md) | 口语 2026 年 5–8 月题库 review |

## research/ — 标准 · 研究

| 文档 | 用途 |
| --- | --- |
| [china-scoring-standard-1-1.md](research/china-scoring-standard-1-1.md) | 中国区评分标准(1.1) |
| [writing-task1-import-research.md](research/writing-task1-import-research.md) | 写作 Task1 导入研究 |
| [adaptive-weak-question-training-1-3.md](research/adaptive-weak-question-training-1-3.md) | 自适应弱项训练(1.3) |
| [codex-token-billing-balance-deduction-1-4.md](research/codex-token-billing-balance-deduction-1-4.md) | Codex token 计费 / 扣费(1.4) |

## superpowers/ — agent 设计 / 计划

需求 → 计划 → 设计的工作流文档。见 [superpowers/index.md](superpowers/index.md)。

## readme-assets/

README 用到的截图素材,非文档。
