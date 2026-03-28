#pragma once

#include <QMainWindow>
#include <QThread>
#include <QTextEdit>
#include <QPushButton>
#include <QLabel>
#include <QProgressBar>
#include <memory>

#include "common/interview_state.h"

namespace interview {
namespace session {
    class DialogSession;
}

namespace ui {

using common::InterviewState;

/**
 * @brief 主窗口
 *
 * 应用程序唯一主窗口，展示对话内容、面试进度和状态。
 * 通过 ConfigDialog 收集配置后创建 DialogSession，在独立线程中运行会话。
 */
class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);
    ~MainWindow();

private slots:
    void OnNewSession();   // 弹出 ConfigDialog，配置并准备新会话
    void OnStartSession(); // 启动已配置的会话（开始面试）

    // 由状态机回调触发，跨线程安全地刷新 UI
    void OnStateChangedFromMachine(InterviewState old_state, InterviewState new_state);

private:
    void SetupUi();
    void SetupMenuBar();
    void SetupToolBar();
    void SetupCentralWidget();
    void ApplyGlobalStyle();
    void UpdateUIState(InterviewState state);  // 根据状态启用/禁用控件
    QString GetStateText(InterviewState state); // 状态枚举转可读文本
    void AppendMessage(const QString& text, const QString& color = "black"); // 追加对话内容

    // --- UI 控件 ---
    QTextEdit*    message_area_;       // 对话内容显示区
    QLabel*       status_label_;       // 当前状态文字提示
    QProgressBar* progress_bar_;       // 面试进度（已答题数/总题数）
    QPushButton*  start_button_;       // 开始面试
    QPushButton*  new_session_button_; // 新建会话

    // --- 业务对象 ---
    std::unique_ptr<session::DialogSession> session_; // 当前面试会话
    std::thread session_thread_;                      // 运行 DialogSession 的后台线程

    // --- 会话配置（由 ConfigDialog 填入）---
    QString candidate_name_;
    QString resume_path_;
    int     min_questions_;
};

} // namespace ui
} // namespace interview
