# P1 语音撕裂 —— 先加日志抓真相（停止盲猜）

> 给 Codex。撕裂已被误诊两次（transaction 竞态、readyState 缓冲），都失败。
> **这一刀不修，只加诊断日志**，让用户真说一句话抓到撕裂瞬间的真实事件序列，再据此一刀治本。

## 已排除（不要再往这些方向修）
- 后端 `tts_audio_view` 是整段 `FileResponse`（views.py ~305），**不是流式**，撕裂不是后端传输欠载。
- signal sampler 默认关闭、无 `createMediaElementSource`，**不是 Web Audio 图问题**。
- transaction/playbackId 竞态——改过无效，**不是它**。
- 现象：第一题（固定音频）完美；动态 TTS 题（follow-up）撕裂 → 撕裂是 streaming follow-up 引入的回归。

## 任务：给 examinerAudio 元素挂全事件日志（只加日志，不改播放逻辑）

在 `playExaminerTurn` 真正拿到 `audio = $("examinerAudio")`、设好 src 后（app.js ~2347），
给这个 audio 元素挂上**所有关键媒体事件**的 console 日志，每条带高精度时间戳：

```js
// 仅诊断：撕裂事件探针
const EV = ["loadstart","emptied","stalled","suspend","waiting","playing",
            "pause","play","seeking","seeked","ratechange","ended","error",
            "canplay","canplaythrough","timeupdate"];
const t0 = performance.now();
const probe = (e) => {
  // timeupdate 太频繁，只在异常时打：currentTime 不前进/回退才打
  console.log(`[AUDIO ${Math.round(performance.now()-t0)}ms] ${e.type}`,
    { ct: audio.currentTime.toFixed(2), paused: audio.paused,
      readyState: audio.readyState, networkState: audio.networkState,
      buffered: audio.buffered.length ? audio.buffered.end(audio.buffered.length-1).toFixed(2) : 0 });
};
EV.forEach((t) => audio.addEventListener(t, probe));
```

要点：
- **timeupdate** 单独处理：只在「currentTime 不前进或回退」时打日志（撕裂时声音卡住，currentTime 会停或跳）。
- 日志要能看出撕裂发生时：是 `waiting/stalled`（欠载）、还是 `pause→play`（被中途暂停）、
  还是 `emptied/loadstart`（src 被重设/load 重来）、还是 `seeking`（被 seek）。
- 探针在每次播放结束（ended/error/被切换）时移除监听，避免泄漏。

## 验收（用户做）
1. `node --check web/static/app.js` 通过。
2. 起服务，**真麦克风真人** P1 连点到出现撕裂的那题。
3. **把 Console 从该题开始播放到撕裂瞬间的完整日志贴出来**（带时间戳那些 `[AUDIO ...ms]` 行）。

## 红线
- **只加日志，不改任何播放/状态机逻辑**。
- 不碰后端、不碰 realtime、不碰 transaction。
- 日志加完即停，交用户跑，把 console 输出贴回来定位。

## 定位后的预案（指挥据日志判断，先不做）
- 若见 `waiting/stalled` → blob 整段预取（fetch→createObjectURL→src），播放源本地完整不欠载。
- 若见 `pause→play` 成对 → 有代码在播放中途 pause，揪出那个调用点删掉。
- 若见 `emptied/loadstart` 中途 → audio.src 被重复设置/load 重来，去重。
- 若见 `seeking` → 有代码在播放中改 currentTime，去掉。
