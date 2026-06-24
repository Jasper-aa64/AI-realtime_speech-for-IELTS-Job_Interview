# SPEC — AI 路由实测(确认真走 Aiapis gpt-5.4-mini,而非 fallback 伪装)

> 给 Codex / 用户。本轮 AI 路由改造已落地(services.py 四档 chain/http/codex/fallback,默认 gpt-5.4-mini 走 HTTP)。
> 代码已过 py_compile / manage.py check / 48 测试。**唯一缺的是:用真实 Aiapis key 跑一轮,证明真走了 HTTP provider。**
> 指挥(本会话)不碰凭据、不跑实测;本 SPEC 定判据与步骤,凭据注入由用户做。

## 0. 红线:凭据只由用户注入,不写进任何文件/日志/git
- `AI_HTTP_BASE_URL` / `AI_HTTP_API_KEY` 从 cc-switch 的 Aiapis 取,**用户用 `export` 注入 runserver 那个 shell**。
- 严禁把 key 写进 SPEC、prd、测试、commit、log。实测产生的截图/日志若含 key,先脱敏。

## 1. 实测前置(用户做)
```bash
# 在启动 runserver 的同一个 shell:
export AI_HTTP_BASE_URL="<Aiapis base url>"
export AI_HTTP_API_KEY="<Aiapis key>"
export SPEAKING_AI_CALL_MODE=http          # http=只走HTTP,失败显式fallback,便于判定真假
export SPEAKING_AI_MODEL=gpt-5.4-mini
# 确认注入成功(只看是否非空,别打印 key):
[ -n "$AI_HTTP_BASE_URL" ] && [ -n "$AI_HTTP_API_KEY" ] && echo "creds present" || echo "MISSING"
```
> 为什么用 `http` 而非 `chain` 实测:`chain` 会在 HTTP 失败时静默落到 Codex/fallback,掩盖问题;`http` 模式失败就显式报错,实测才能暴露真相。验收通过后再按需切回 `chain`。

## 2. 判定铁证(核心 —— 区分真 gpt-5.4-mini vs fallback 伪装)
代码已确认的 metadata 字段(services.py):
- **HTTP 真成功**:`backend == "http_api"` 或 `"http_api_stream"`, `provider == "openai_compatible_http"`,且有非零 token usage(`prompt_tokens`/`completion_tokens` 或 `input_tokens`/`output_tokens`)。
- **Fallback(伪装失败)**:`source == "fallback"` / `backend == "fallback"` / `status == "fallback"`,无 token 计数。

**实测通过 = 看到 provider=openai_compatible_http + backend=http_api/http_api_stream + 非零 token;**
**实测失败 = 出现任何 fallback 标记,或 model 不是 gpt-5.4-mini。**

> 注意:`model` 字段是本地配置值,只能辅助确认配置,不能单独证明真实调用。是否真的花 token,以 provider/backend + 非零 usage 为准。

## 3. 实测范围(每条都要看到 §2 的铁证)
1. **P1 follow-up**:真人 P1 答一题 → 追问生成 → 查该 turn 的 usage/metadata。
2. **P3 follow-up**:同上,P3 路径。
3. **P3 from P2**:P2 → P3 衍生题路径。
4. **流式 follow-up(SSE)**:确认流式路径也走 HTTP(首字 + 最终 metadata)。
5. **Speaking report**:整场报告生成,查 backend 字段。
6. **逐题 Band 7 / coaching batch**:查 provider 标记。

## 4. 取证方式(二选一,Codex 给具体入口)
- **优先 CLI/脚本**:`scripts/validate_speaking_ai_routing.py` 已提供。
  - 快速低成本验收:
    ```bash
    .venv-django/bin/python scripts/validate_speaking_ai_routing.py --cases quick --model gpt-5.4-mini
    ```
    覆盖 P1 follow-up / P3 follow-up / streaming follow-up。
  - 全量验收(更耗 token):
    ```bash
    .venv-django/bin/python scripts/validate_speaking_ai_routing.py --cases all --model gpt-5.4-mini
    ```
    覆盖 P1 / P3 / P3-from-P2 / streaming / report / Band7-coaching。
- **否则浏览器**:真麦克风真人跑 P1/P3,从 DevTools Network 看 follow-up/report 响应里的 usage/metadata 字段,或后端日志里的 provider 标记。
- **延迟数字**:顺便记 `latency_seconds`(对照历史:HTTP P50 约 4.66s,最快 1.46s),写进汇报。

## 5. 交付(Codex/用户汇报回指挥)
- [ ] §3 六条路径各贴一行铁证:`provider` / `model` / `latency_seconds` / token 数(key 脱敏)。
- [ ] 若某条仍 fallback:贴 `error` 字段,定位是 base_url 格式 / 鉴权 / 超时 / 端点不兼容 哪一类。
- [ ] 实测用的 `SPEAKING_AI_CALL_MODE` 值;通过后是否切回 `chain` 的建议。
- [ ] 不提交 db.sqlite3;不提交含 key 的任何产物。

## 6. 实测通过后(不在本轮做,记录为下一刀)
- 切回 `SPEAKING_AI_CALL_MODE=chain`(HTTP 优先 + Codex 兜底)做生产默认。
- 回到挂起的 Howler/TTS 收尾(`docs/SPEC-exp5-howler-reuse-and-report.md` 第一段)。
- 实验5 Word 报告(同上 SPEC 第二段)。
