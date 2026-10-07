# IELTS Studio 桌面端（Qt）

Qt 6 + QtWebEngine 外壳，加载服务器上的 IELTS Studio 网页界面。设计与计划见
`docs/superpowers/specs/2026-10-05-qt-desktop-studio-design.md`、
`docs/superpowers/plans/2026-10-05-qt-desktop-shell.md`。

## 构建

需要 `brew install qt`（Qt 6，含 WebEngine）。在仓库根目录：

    cmake -S desktop -B build-desktop -DCMAKE_PREFIX_PATH="$(brew --prefix qt)" -DCMAKE_BUILD_TYPE=Debug
    cmake --build build-desktop -j
    ctest --test-dir build-desktop --output-on-failure

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

模拟面试通过 QWebChannel 的 `studioNative.capabilities()` 确认桌面能力；普通浏览器没有面试模式。当前支持文字回答、题库、定制问题和持久记录，`native_audio` 明确为 false，尚未连接真实语音引擎。Qt 注入其自带的 WebChannel JavaScript 资源，不依赖 UA 或网址参数来授权桌面功能。

登录状态、localStorage 存在 Qt 的持久化 profile `IELTSStudio` 里
（`~/Library/Application Support/IELTS Studio/IELTS Studio/QtWebEngine/IELTSStudio/`）。
退出时 `main()` 先销毁窗口再销毁 profile，Chromium 才会把 Cookie 落盘；所以主窗口的关闭事件不直接结束进程，而是让事件循环退出。
