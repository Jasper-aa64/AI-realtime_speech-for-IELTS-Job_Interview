# 修复 stdin 缓冲区污染导致主菜单循环 Unknown menu option

## Goal

用户在 P2 session 的错误时机粘贴了多行文字，导致 stdin 缓冲区残留内容，
P2 结束回到主菜单后 getline 把残留行当菜单选项读入，循环打印 "Unknown menu option."

## Root Cause

`src/main_ielts.cpp` 主循环在每次 `std::getline(std::cin, choice)` 前没有清空 stdin。
任何 session 内部没消费完的 stdin 内容都会泄漏到主菜单循环。

## Fix

### 方案（最小改动）

在 `src/main_ielts.cpp` 的主菜单读取前加 stdin drain：

```cpp
// drain any leftover stdin content before reading menu choice
{
    std::string discard;
    while (std::cin.rdbuf()->in_avail() > 0) {
        std::getline(std::cin, discard);
    }
}
PrintMenu();
std::string choice;
std::getline(std::cin, choice);
```

或者用 POSIX `tcflush`（更彻底）：

```cpp
#include <termios.h>
// ...
::tcflush(STDIN_FILENO, TCIFLUSH);
PrintMenu();
std::string choice;
std::getline(std::cin, choice);
```

`tcflush` 更可靠（直接丢弃内核 tty 缓冲区），推荐使用，只需在文件顶部加 `#include <termios.h>`。

### 同时修 Part2Session

`src/ielts/part2_session.cpp` 的 `RecordSpeech` 结束时也做一次 `tcflush`，避免录音期间 EnterPressed() 消费不完整导致残留：

```cpp
// at end of RecordSpeech(), after getline for transcript
::tcflush(STDIN_FILENO, TCIFLUSH);
```

## Acceptance Criteria

* [ ] 粘贴多行文字后，P2 session 结束回到主菜单，只显示一次菜单，不循环打印 "Unknown menu option."
* [ ] `cmake --build build` 无 error
* [ ] `ctest` 通过

## Out of Scope

* codex 评分失败问题（另外的 bug）
* Realtime STT 断连问题
