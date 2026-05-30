# 软件构造作业交付索引

本目录收纳 IELTS Web 产品重构线对应的软件构造实验材料。整体叙事保持一致：

```text
现有 Django + web/static 浏览器产品 = baseline
C++ audio_core / WASM / realtime gateway = 增量加速层
旧批处理链路 = fallback
```

核心原则：不推倒成熟产品，不改变 P1/P2/P3、写作、报告、语料库、Takeaway 等现有功能设计；作业材料展示的是在现有系统上做架构重构、TDD 验证、坏味道治理和开源复用。

## 交付清单

| 实验 | 主题 | 文档 | 演示/汇报 | 验证入口 |
| --- | --- | --- | --- | --- |
| 实验1 | 原始课程报告 | `软件构造_实验1_报告.docx` | - | 人工检查 |
| 实验2 | 设计模式与类设计 | `重构总体架构.md`、`实验2_设计文档.md`、`实验2_类图.puml` | `软件构造-实验2.pptx` | `scripts/run_experiment2_design_validation.sh` |
| 实验3 | TDD 验证 | `实验3_TDD验证报告.md` | `软件构造-实验3.pptx` | `scripts/run_experiment3_tdd_validation.sh` |
| 实验4 | 重构坏味道 | `实验4_重构报告.md` | `软件构造-实验4.pptx` | `scripts/run_experiment4_refactor_validation.sh` |
| 实验5 | 开源复用与 WASM | `实验5_开源复用与WASM方案.md` | `软件构造-实验5.pptx` | `scripts/run_experiment5_reuse_validation.sh` |

## 代码证据

| 证据 | 说明 |
| --- | --- |
| `backend_django/apps/ai/provider_adapters.py` | 实验2 Python 侧 Strategy / Adapter / Template Method / Chain of Responsibility 重构 |
| `include/ielts/audio_core.h`、`src/ielts/audio_core.cpp` | 实验4 C++ `audio_core` 纯核抽取 |
| `third_party/libfvad/` | 实验5 开源库复用，BSD-3-Clause，基于 WebRTC VAD |
| `src/ielts/audio_core_wasm.cpp` | C++ 到 WASM 的 C ABI adapter |
| `web/static/wasm/` | WASM demo、AudioWorklet demo、feature-flagged speaking preprocessor |
| `scripts/run_experiment*_*.sh` | 实验2-5 可重复验证入口 |

## 一键验证

运行总验证：

```bash
scripts/run_software_construction_deliverables_validation.sh
```

该脚本会检查交付文件是否齐全，并依次运行实验2、实验3、实验4、实验5的验证脚本。

如只验证单个实验：

```bash
scripts/run_experiment2_design_validation.sh
scripts/run_experiment3_tdd_validation.sh
scripts/run_experiment4_refactor_validation.sh
scripts/run_experiment5_reuse_validation.sh
```

## Git 注意事项

- `web/static/wasm/audio_core_wasm.js` 和 `web/static/wasm/audio_core_wasm.wasm` 是生成产物，必须保持 ignored。
- `backend_django/db.sqlite3` 是本地测试数据，不属于本交付索引任务。
- PPTX/DOCX 是课程交付物，可随本目录一起归档。
