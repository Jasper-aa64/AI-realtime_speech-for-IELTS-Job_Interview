# SPEC — 实验五收尾(howler 复用)+ Word 实验报告

> 给 Codex。两段交付,**先收尾 howler,再写报告**。指挥(本会话)不写生产代码,只定目标/边界/验收。
> 角色:用户=设计/验收;Codex=实现。本 SPEC 是唯一权威需求来源。

---

## 背景(已确认事实,别重新假设)

- 主运行时已落地:Django 后端 + `web/static` 单页前端 + C++/WASM 音频层 + ASGI/Channels(4.3.2 已装)WebSocket。
- 实验五主题:**复用开源软件资源进行软件构造**。本项目真实复用两个开源资源:
  1. **libfvad**(WebRTC VAD,BSD-3-Clause)——已编译进 `audio_core` → WASM,跑在浏览器录音链路。
  2. **howler.js**(MIT)——已引入 `web/static/vendor/howler.min.js`,正在替换手搓的 examiner TTS 播放层。
- P1 语音撕裂根因已确诊:前端直接播 VolcEngine 原始 mp3,后端 `?stable=1`→`afconvert`→m4a 的浏览器友好转码路径写好了但没接上;手搓播放器(`playbackId`/`playbackKey`/transaction/sampler)越补越乱。
- 决策:**不再修旧手搓播放器**,改用 howler.js 做稳定播放层 = 既止血,又让实验五从"硬说复用"变成"真复用"。

---

## 第一段:收尾 — examiner TTS 播放层切到 howler.js

### 目标
用 howler.js 封装一个干净的 `ExaminerAudioPlayer`,P1 流程只接业务事件,彻底退役底层手搓播放细节。

### 必须实现的接口(业务只接这层)
```text
ExaminerAudioPlayer
  load(turnId, stableUrl)   // 预加载,内部 new Howl({src,preload})
  play(turnId)              // 播放;turnId 不匹配当前则忽略(防串台)
  stop()                    // 停止并释放当前
  unload()                  // 释放所有 Howl 资源,防泄漏
  事件: onReady / onPlay / onEnd / onError
```
- 内部用 `Howl`:优先 Web Audio,自动 fallback HTML5;用 `onload/onplay/onend/onloaderror/onplayerror`。
- **播放源只用 stable URL(`?stable=1`→m4a)或 blob;VolcEngine 原始 mp3 不作主播放源。**
- 第一题固定音频(`FIXED_EXAMINER_AUDIO_URLS`)也走这层,确认不被弄坏。

### 必须退役/删除(这是"收尾"的核心,别只加不删)
- 旧的 `playbackId` / `playbackKey` / `createExaminerPlaybackTransaction` / 事务校验、手写 `waitForAudioReady` readyState 轮询、signal sampler/trace 这些**与撕裂无关、互相打架**的机制。
- `app.js` 现有调用点(已定位):`stopExaminerPlayback`(1401/1544/2136/2276/2426/6831/6878)、`playExaminerTurn`(2395)、`resolveExaminerAudioPlaybackUrl`、`stableExaminerAudioUrl`(1867/1880)、`playExaminerAudioBuffer` —— 统一收敛到 `ExaminerAudioPlayer`,删掉冗余分支。
- P1 业务状态机只保留 4 态:**TTS ready / play started / play ended / play failed**。不再关心 `readyState`/`currentTime`/buffer/stalled。

### 红线
- 后端 `?stable=1`/`afconvert→m4a` 这条路保留;转码失败 fallback 回 mp3 时**带 metadata 明确标记降级**,不伪装成功。
- 不碰 realtime/ASR/WASM 预处理链路;不扩展 `web/ielts_server.py`;不提交 `db.sqlite3`;key 不入代码/日志/git。
- howler 走本地 `vendor/howler.min.js`,不引 CDN(离线可演示)。

### 验收(用户真人验)
- [ ] `node --check web/static/app.js` 通过,Console 无报错。
- [ ] **真麦克风真人** P1:第 1 题(固定音频)正常;第 2 题起每题考官语音连续、无撕裂、无中间断。
- [ ] 追问题(动态 TTS)连续无撕裂。
- [ ] 起播延迟可接受(stable 转码 + howler 预加载后 ≤1-2s)。
- [ ] 旧手搓播放机制确已删除(grep 不到 transaction/playbackId 残留分支),代码净减。

---

## 第二段:写 Word 实验报告(实验五)

### 输出
- 文件:`软件构造/软件构造_实验5_报告.docx`(**Word/.docx**)。
- **格式严格对齐** `软件构造/软件构造_实验1_报告.docx`:Codex 必须先打开实验1报告,镜像它的标题层级、字体、章节编号、封面/页眉页脚风格。
- 已有的 `软件构造/实验5_开源复用与WASM方案.md` 作为内容素材来源,但报告要**重新组织、写长、写实**,不是把 md 贴进去。

### 篇幅要求
**写长一点、写充实**:每章展开论述,配表格 + 架构图(可用文字框/ASCII 或导出图)+ 关键代码清单。目标正文不少于实验1报告的体量(数千字级),不要写成提纲。

### 必含章节(可按实验1的编号风格调整)
1. **实验目的** —— 复用开源资源进行软件构造的目标与意义。
2. **实验环境** —— OS / 浏览器 / Django / Emscripten(emsdk)/ Node 版本等。
3. **复用资源选型与许可证合规**
   - libfvad(BSD-3-Clause)、howler.js(MIT)、Emscripten 工具链;来源、版本、license、为什么选它们。
4. **为什么复用而非手搓**(重点,呼应实验主题)
   - 手搓 examiner 播放器的真实债务:`playbackId`/`playbackKey`/transaction/sampler 竞态、修一处冒一个新 bug、语音撕裂久治不愈;复用 howler 后业务只剩 4 态。用真实经历论证"复用稳健实现"的价值。
5. **集成架构**
   - C++ `audio_core` + libfvad → Emscripten → WASM → 浏览器录音预处理(默认路径 + baseline 降级);
   - howler.js → `ExaminerAudioPlayer` → 播放 stable(m4a)音频;
   - 两条复用链路如何嵌进 Django + SPA 主线。
6. **关键实现与代码说明** —— 贴关键片段(WASM 加载、VAD 调用、`ExaminerAudioPlayer` 封装、后端 `?stable=1`/afconvert)。
7. **测试与验证** —— 真人验收结果、撕裂前后对比、`node --check`、后端测试规模(约 290 个 `test_`)、WASM 产物大小(`audio_core_wasm.js` 68KB / `.wasm` 144KB)。
8. **遇到的问题与解决** —— 原始 mp3 撕裂根因 → stable m4a → howler 复用的完整定位过程(诚实写,包括误诊与纠偏)。
9. **复用收益量化** —— 代码行数变化(删除手搓播放机制后净减)、消除的 bug 类别、可维护性提升。
10. **实验结论与心得** —— 复用 vs 手搓的工程权衡总结。

### 红线
- **数字不许编造**:验收数据、行数、延迟用真实测得值;拿不到的标"待测",不写假数。
- 许可证信息要准确(libfvad=BSD-3,howler.js=MIT)。
- 不夹带 `db.sqlite3`;不泄露任何 key。
- 报告里截图/数据若引用运行结果,以真人验收那次为准。

### 验收(用户)
- [ ] `软件构造/软件构造_实验5_报告.docx` 能用 Word 正常打开,格式与实验1一致。
- [ ] 篇幅充实,十章齐全,有表格 + 架构图 + 代码清单。
- [ ] 复用主题贯穿(libfvad + howler.js + Emscripten),数据真实。
