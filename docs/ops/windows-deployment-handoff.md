# HANDOFF — 迁移到办公室 Windows 常驻部署

> 本文件给**在办公室 Windows 机器上新开的 Claude Code 会话**。项目从一台 macOS 开发机整体迁来,之后**开发与常驻部署都在这台 Windows 上**。
> 目标:在这台常驻 Windows 上,用 **Tailscale** 提供一个**固定不变、不掉线**的访问地址(自己设备私有访问 + 可选公网 Funnel),后端 Django + AI worker 做成**开机自启 + 崩溃自启**的服务。

## 0. 角色与工作方式(沿用)
- 用户 = 设计者 / 指挥 / 验收。助手(你)= 指挥/导演:读代码、定方案、写 SPEC、下指令;**尽量不亲自写生产代码**(用户明确要的提示词除外)。实现交给 Codex。报告类是 FYI,用户自己验收。
- 这是延续的协作约定,保持即可。

## 1. 这个项目是什么(现状)
- IELTS 雅思口语/写作练习 Web 产品。后端 **Django 5.2 + Channels(ASGI/WebSocket)+ WSGI 兜底**,前端 `web/static` 单页 SPA,音频预处理用 **C++ → Emscripten → WASM**(产物已预编译入库,见 §3,**无需在本机装 emsdk/重编**)。
- apps:`accounts / billing / speaking / writing / ai / common`。
- AI 路由:`apps/ai/provider_adapters.py`(Strategy/Adapter/Template Method/Chain of Responsibility)。默认走 **OpenAI 兼容 HTTP provider**(模型 `gpt-5.4-mini`),Codex CLI 仅兜底。
- **durable AI worker**(`manage.py run_ai_worker`)是产品运行时的一部分:不开 worker,写作评分会一直卡"已排队"。

## 2. 迁移清单(用户已用文件传输/UU远程 把项目搬到本机)
到本机后,新会话先核对:
- [ ] 代码已就位(含 `backend_django/`、`web/static/`、`docs/`、`.trellis/`)。
- [ ] **`backend_django/db.sqlite3` 是从原机拷来的最新实时库**(不是 git 里那份旧快照)——这是用户要保留的现有数据。
- [ ] `web/static/wasm/audio_core_wasm.{wasm,js}` 在(预编译产物,运行时只发文件)。
- [ ] **不要**搬 `.venv-django/`(135M)、`build/`(170M)、`__pycache__`、`node_modules`——这些在 Windows 重建/无需。
- [ ] `requirements-lock.txt` 在(原机 `pip freeze`,用于复现环境)。

### 2.1 在 Windows 重建运行环境
- 装 **Python 3.13.x**(原机用 3.13.12,尽量对齐)。
- 建 venv 并装依赖:
  ```powershell
  py -3.13 -m venv .venv-django
  .\.venv-django\Scripts\python -m pip install -U pip
  .\.venv-django\Scripts\python -m pip install -r requirements-lock.txt
  ```
- 装 **ffmpeg**(`choco install ffmpeg` 或官网 zip 加 PATH)。项目**本来就依赖 ffmpeg**(VolcEngine ASR),且 afconvert 移植后也用它(见 §4)。
- 迁移自检:
  ```powershell
  cd backend_django
  ..\.venv-django\Scripts\python manage.py migrate
  ..\.venv-django\Scripts\python manage.py check
  ..\.venv-django\Scripts\python manage.py test apps.writing apps.ai
  ```

## 3. 已确认的可移植性结论(别重新假设)
- **WASM 产物已入库**,运行时只是静态发文件 → **Windows 不用装 emsdk、不用编译 C++**。
- **依赖全跨平台**(Django/channels/daphne/DRF/cryptography 等都有 Windows wheel)。
- **唯一 macOS-only 运行时依赖 = `afconvert`**,仅出现在 `backend_django/apps/speaking/tts_services.py`(考官音频转 m4a),且已是 `shutil.which()` 可选探测。→ 见 §4 港口任务。
- 启动脚本 `scripts/start-local-stack.sh` 是 bash + 读 `~/.cc-switch/cc-switch.db` 取 key,**Windows 不适用**,要新写(§4)。

## 4. Windows 港口任务(派给 Codex 实现;方案=原生 Windows,不用 WSL)
> 选原生 Windows 而非 WSL:Tailscale 直接 `funnel/serve` 到 `localhost:8767`,网络最干净、最不易掉。WSL 多一层端口转发,反而易断。

1. **afconvert → ffmpeg 跨平台**:`tts_services.py` 里把 macOS-only 的 `afconvert` 改成用已有的 **ffmpeg** 做等价转码(mp3→浏览器友好 m4a/aac)。保留"转码失败带 metadata 明确标记降级、不伪装成功"的红线。非 mac 平台不得因缺 afconvert 而静默退化(要么 ffmpeg 成功,要么显式标记)。
2. **PowerShell 启动脚本** `scripts/start-local-stack.ps1`(对标 .sh):
   - 启动 Django(优先用 **daphne** 跑 ASGI:`daphne -b 127.0.0.1 -p 8767 config.asgi:application`,Channels/WebSocket 才稳;runserver 仅开发用)。
   - 启动 `manage.py run_ai_worker`(stop-file 用 Windows 临时目录,别用 `/tmp`)。
   - **key 走环境变量/`.env`(gitignored),不读 cc-switch.db**:`AI_HTTP_BASE_URL / AI_HTTP_API_KEY / AI_HTTP_MODEL / AI_HTTP_TIMEOUT_SECONDS`、`SPEAKING_AI_CALL_MODE=chain`、`SPEAKING_AI_MODEL=gpt-5.4-mini`。
   - 设 `DJANGO_ALLOWED_HOSTS` / `DJANGO_CSRF_TRUSTED_ORIGINS` 为本机 Tailscale 固定域名(见 §5)。
3. **常驻服务(核心:不掉)**:用 **NSSM** 把 Django、worker 各包成一个 Windows 服务,设 `AppExit ... Restart` + 开机自启;或用任务计划程序(开机触发 + 失败重启)。提供一键安装/卸载脚本。
4. **跨平台路径排雷**:扫一遍硬编码 POSIX 路径(如 `/tmp`)、文件编码、换行,改成 `tempfile`/`pathlib`。

## 5. Tailscale 固定地址(用户的手 + 你接本机命令)
- tailnet:`tail46b1c.ts.net`,账号 `ljm040309@`。本机上线后会有固定名(原有离线 Windows 节点叫 `jm-1`,可复用)。
- **一次性管理台开关(tailnet 级,用户在浏览器做)**:
  1. `https://login.tailscale.com/admin/dns` → 启用 **HTTPS Certificates**(serve/funnel 都依赖)。
  2. 公网才需要:启用 **Funnel** 属性(开 HTTPS 后跑 `tailscale funnel` 会给确切开启链接)。
- 本机接入(你执行):
  - 需求1 自己设备私有:`tailscale serve --bg --https=443 localhost:8767` → `https://<本机名>.tail46b1c.ts.net`。
  - 需求2 任意浏览器公网:`tailscale funnel --bg 8767` → 同一固定地址转公网。
- 把该固定域名写进 `DJANGO_ALLOWED_HOSTS` + `DJANGO_CSRF_TRUSTED_ORIGINS`(地址固定,不用通配)。

## 6. 红线(持续有效)
- **凭据(ASR/AI key)绝不进代码、日志、git**,只走环境变量/`.env`(gitignored)。截图/日志含 key 先脱敏。
- fallback 必须带 metadata 明确标记,**不得伪装 AI 成功**。
- 不扩展 `web/ielts_server.py`(旧入口,弃用)。
- 原始 C++ 面试系统须在部署产品里有真实运行存在(当前=WASM 音频预处理)。
- howler.js 走本地 `vendor/`,不引 CDN。许可证:libfvad=BSD-3,howler.js=MIT。
- `db.sqlite3` 现按用户决定**保留在仓库**(示例用户数据);但**真实用户数据/key 仍不得入库**。

## 7. 待办 / 在途(迁移后接着干)
- **拼写错词训练(spelling drill)**:Codex 刚实现(`apps/writing/spelling_services.py`、`models.py SpellingDrillWord`、migration `0008`、`web/static/spelling-drill.js`、`test_spelling_drill.py`),**尚未用户验收**。SPEC=`docs/SPEC-writing-task1-chart-facts-and-prompt.md` 同级的 `docs/SPEC-writing-spelling-drill.md`(掌握线已定为连对 **4** 次)。迁移后跑测试 + 真机验收。
- **AI 路由实测**:用真实 Aiapis key 证明真走 HTTP provider(判据:`provider=openai_compatible_http` + `backend=http_api/http_api_stream` + 非零 token)。脚本 `scripts/validate_speaking_ai_routing.py`。
- **Task1 图表事实卡**:管线已入库;待导入剑雅授权图 → 跑 `scripts/generate_task1_chart_facts.py` → 用故意写错数据的作文验 `data_accuracy_notes` 能否抓错。版权图是用户的手。
- 实验 2~5 报告:已完成,翻篇。

## 8. 迁移后第一步(建议顺序)
1. 重建 venv + 装 ffmpeg + `migrate`/`check`/`test`(§2.1)。
2. 先用 `runserver`/`daphne` 本地 `127.0.0.1:8767` 起来,确认能打开、能登录、能批改。
3. 派 Codex 做 §4 港口(afconvert→ffmpeg、ps1 启动、NSSM 服务)。
4. 用户开 §5 管理台 HTTPS(+Funnel),你接 `tailscale serve/funnel` + 收紧 host。
5. 验收拼写训练 + AI 路由实测(§7)。
