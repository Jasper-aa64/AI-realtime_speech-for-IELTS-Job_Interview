# Goal 规格：流式考官追问 Phase 2 —— realtime ASR over WebSocket（ASGI）

> 大 goal 第二阶段。给实现方（Codex）。用户负责 review + 验收 + ASR 端点细节。
> 传输通道已定：**ASGI + WebSocket（Channels）**。本规格定目标、边界、红线、验收。
> ASR 端点 URL / 鉴权 / 流式协议细节由用户与 Codex 实现时确定，本规格不写死。

## 已就位（地基，Codex 已铺）

- Phase 1 闭环：SSE 流式追问 + TTS pipeline，首字实测 ~2.11s（commit `b458a70`）。
- ASR provider 地基：`speaking/realtime_asr.py` + `volcengine_asr.py`，
  `stream_pcm_chunks()` 支持 fake websocket 流式 `interim/final/done`（commit `46ea16d`）。
- 浏览器 PCM：`speaking_audio_preprocessor.js` Float32→16k PCM16，可选 `onPcmFrame`
  回调，默认不改现有录音（commit `c0126ec`）。
- 现状：`config/asgi.py` 与 `wsgi.py` 都在；**Channels 未安装**。

## Phase 2 目标

把"边说边出字"通过 **WebSocket** 真正接通：浏览器流式送 16k PCM → 后端 WS 消费 →
realtime ASR 流式转写 → 实时回前端显示 → 串到 Phase 1 流式追问 → TTS。

## ⚠️ 最高红线：ASGI 迁移不得破坏现有同步栈（baseline）

引入 Channels/ASGI 是本 goal 最大风险点。必须满足：

1. **现有所有同步 HTTP 视图、API、静态托管行为完全不变**。WSGI 时代能跑的，ASGI 下照样跑。
2. **`runserver` / 测试 / 现有部署不被破坏**。全量 `manage.py test`（当前 264+）必须继续全绿。
3. **WebSocket 是新增叠加通道**，不替换任何现有 HTTP 路径。录音「录完上传批处理」主流程保留为 fallback。
4. **ASGI/Channels 配置走可回退路径**：若 Channels 出问题，同步栈仍可独立运行。
5. Channels 作为新依赖，需写进 requirements 并说明；不偷偷引入。

## 范围（分小步，每步独立可验、可回滚）

- **2.1 ASGI/Channels 接入**：装 Channels、配 `asgi.py` ProtocolTypeRouter（http→现有 Django，
  websocket→新 consumer）。**此步不加业务逻辑**，只验"同步栈零回归 + 一个 ping WS consumer 能连"。
- **2.2 PCM 上行 WS**：浏览器 `onPcmFrame` → WS 上行 → 后端 consumer 收 PCM chunks。先只验"帧到达后端"。
- **2.3 ASR 串联**：consumer 把 PCM 喂 `stream_pcm_chunks()` → 转写 `interim/final` 实时 WS 回前端 →
  前端边说边出字。
- **2.4 串 Phase 1 追问**：final 转写 → 触发 Phase 1 流式追问 SSE/同机制 → TTS。整条打通。
- **2.5 首字+降级实测**：DevTools 量「停说→追问首字」端到端；演示 WS/ASR 失败无缝回落批处理。

## 红线 / 边界

- ASR key / 鉴权绝不进代码、日志、git；全走环境变量（沿用 `realtime-asr/status` 的 secret-safe 模式）。
- fallback / 降级必带明确标记，不伪造成功。
- 不夹带工作区现有 WIP 脏文件（corpus_services.py / speaking tests / app.js / db.sqlite3）；分步独立提交。
- 不做发音评测、不做「能打断」全双工（学生说完考官接，不是双向打断）。
- 本 goal 先**本地端到端跑通**；生产级 Linux ASGI 部署（uvicorn/daphne + 进程管理）单列说明，不强求一次到位。

## 验收标准（用户验收用）

- [ ] 2.1 后同步栈零回归：全量 `manage.py test` 全绿、`manage.py check` 通过、现有页面/ API smoke 正常。
- [ ] 边说边出字：浏览器实测，说话时转写实时滚动。
- [ ] 端到端首字延迟实测：DevTools「停说→追问首字」数字 + 截图。
- [ ] 降级可演示：WS/ASR 中断 → 回落批处理，录音不中断。
- [ ] Channels 依赖入 requirements；ASR 凭据走环境变量未入库。
- [ ] 分步提交（2.1–2.5 各 commit），CHANGES 记录每步结果 + 首字延迟数字。

## 部署备注（说明，不强求本 goal 完成）

ASGI 上 WebSocket 需 uvicorn/daphne 跑（`runserver` 仅开发够用）。生产 Linux 部署、
进程管理、与现有反代的关系，写进 CHANGES 的"部署影响"段，作为后续部署 goal 的输入。
