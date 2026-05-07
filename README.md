# 运行

# 1) 编译
```
cmake --build build -j
```

# 2) 运行命令行程序
```
./build/CppInterviewSystemQt
```

# IELTS Speaking Simulator

新增独立终端入口 `IELTSSpeakingSimulator`，用于 IELTS Speaking P1/P2/P3 模拟、题库动态加载、Codex CLI 评分和 JSON 报告生成。

## 编译 IELTS 目标

如果现有 `build/` 缓存路径不可用，先重新配置一个构建目录：

```
cmake -S . -B build
cmake --build build --target IELTSSpeakingSimulator -j
```

## 运行

```
./build/IELTSSpeakingSimulator --config-file config/default_config.json --data-dir data/ielts --reports-dir reports
```

菜单支持：

```
[1] Full Mock Exam (P1 + P2 + P3)
[2] Practice Part 1 only
[3] Practice Part 2 only
[4] Practice Part 3 only
[5] View last report
[q] Quit
```

题库会在启动时扫描 `data/ielts/part1/*.json` 和 `data/ielts/part2/*.json`。新增 P1 题库 JSON 后重启程序即可加载，无需重新编译。报告写入 `reports/ielts_YYYYMMDD_HHMMSS.json`。
