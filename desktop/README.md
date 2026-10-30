# IELTS Studio 桌面端（Qt）

Qt 6 + QtWebEngine 外壳，加载服务器上的 IELTS Studio 网页界面。设计与计划见
`docs/superpowers/specs/2026-10-05-qt-desktop-studio-design.md`、
`docs/superpowers/plans/2026-10-05-qt-desktop-shell.md`。

## 构建

需要 `brew install qt`（Qt 6，含 WebEngine），以及 vcpkg（classic 模式）装好实时语音引擎的依赖：

    $VCPKG_ROOT/vcpkg install boost-beast boost-thread openssl portaudio spdlog nlohmann-json zlib --triplet arm64-osx

在仓库根目录（`VCPKG_ROOT` 本机是 `~/Desktop/CS/Cplusplus/vcpkg`）：

    cmake -S desktop -B build-desktop -DCMAKE_TOOLCHAIN_FILE=$VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake \
      -DVCPKG_MANIFEST_MODE=OFF -DVCPKG_TARGET_TRIPLET=arm64-osx \
      -DCMAKE_PREFIX_PATH="$(brew --prefix qt)" -DCMAKE_BUILD_TYPE=Debug
    cmake --build build-desktop -j
    ctest --test-dir build-desktop --output-on-failure

引擎库来自 `cmake/voice_engine.cmake`，和根项目共用。

## 品牌图标

网页品牌、AI 助手、网站图标和桌面图标共用
`web/static/assets/brand/studio-brain.svg` 中的粉色圆角大脑。灯泡是网页上的独立悬浮装饰。
SVG 可眨眼，并遵循系统减少动态效果设置；导出的 PNG、ICO、ICNS 保持睁眼。

在 macOS 仓库根目录重建所有图标（需要 `brew install librsvg`，ICNS 使用系统 `iconutil`）：

    python3 scripts/generate_brand_icons.py

非 macOS 可加 `--skip-icns` 更新网页和 Qt 窗口图标。网站 ICO 包含 16、32、48 像素，
触屏图标为 180 像素。桌面 PNG 为 512、1024 像素，ICNS 包含标准 16、32、128、256、512
逻辑尺寸的 1x/2x 图层。构建时 ICNS 放入应用 `Contents/Resources`，由 `CFBundleIconFile`
引用；Qt 窗口图标通过编译进应用的资源读取，无需运行时查找仓库路径。

## 运行

    open "build-desktop/IELTS Studio.app"

- 服务器地址：菜单「IELTS Studio → 服务器地址…」（Cmd+,），默认 `http://127.0.0.1:8767/`。
- 只对这一次运行换服务器：`"build-desktop/IELTS Studio.app/Contents/MacOS/IELTS Studio" --server <url>`。
- 冒烟检查：加 `--smoke`，加载成功打印 `LOAD_OK` 退出码 0，服务器不可达打印 `LOAD_FAIL` 退出码 1，30 秒超时退出码 3。
  测不可达请用普通的空闲端口（如 59999）；9 这类端口会被 Chromium 以 `ERR_UNSAFE_PORT` 拒绝，不算连接错误。
- 调试页面：`QTWEBENGINE_REMOTE_DEBUGGING=9333` 启动后，可用 Chrome DevTools 协议连 `http://127.0.0.1:9333`。
- 隔离验收：加 `--test-profile` 使用不落盘的临时 profile；搭配 `--server http://127.0.0.1:8768/` 验证独立测试服务，不修改已有登录 Cookie。不要同时用同一个持久 profile 启动两个实例。

模拟面试通过 QWebChannel 的 `studioNative.capabilities()` 确认桌面能力；普通浏览器没有面试模式。

## 实时语音（面试模式）

桥上另有 `studioVoice`：`startSession / speak / startListening / stopListening / endSession / markTranscriptShown`，
信号 `stateChanged(state, reason) / partialTranscript / finalTranscript / error(code, message)`。PCM 和凭据都不过桥。
`native_audio` 只有三条都满足才为 true：引擎能初始化（PortAudio 有输入、输出设备）、本机配置里有火山凭据、
麦克风权限已授予；否则网页回落到原来的录音方式。

- 本机配置：默认 `~/.ielts-studio/realtime_voice.json`（权限 600，不进仓库、不经过网页），可用设置项
  `voice/configPath` 改路径。格式同 `config/default_config.json` 的 `ws / dialog / tts / asr` 段，另有可选的
  `voice` 段：`speak_method`（auto / say_hello / chat_tts_text / prompt）、`half_duplex`（keep_alive / silence）、
  `end_smooth_window_ms`、`enable_custom_vad`（默认 true，不开时平滑窗口不生效）、`input_device` / `output_device`
  （设备名包含的文字，空 = 系统默认；蓝牙耳机做输入会切成通话模式，建议填 "MacBook Air"）、`output_gain`、
  `metrics_dir`、`dump_pcm`。
- 有配置文件时，启动会请求一次麦克风权限。
- 计时日志：`~/Library/Logs/IELTS Studio/voice/voice-*.jsonl`（`dump_pcm` 时另有 `mic-*.pcm` 和 `.times`），
  用 `python3 tools/voice_metrics.py <日志>` 汇总；引擎自身日志在同目录 `engine.log`。Qt 注入其自带的 WebChannel JavaScript 资源，不依赖 UA 或网址参数来授权桌面功能。

登录状态、localStorage 存在 Qt 的持久化 profile `IELTSStudio` 里
（`~/Library/Application Support/IELTS Studio/IELTS Studio/QtWebEngine/IELTSStudio/`）。
退出时 `main()` 先销毁窗口再销毁 profile，Chromium 才会把 Cookie 落盘；所以主窗口的关闭事件不直接结束进程，而是让事件循环退出。
