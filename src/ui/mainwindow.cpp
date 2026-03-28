#include "ui/mainwindow.h"
#include "ui/config_dialog.h"
#include "interview/dialog_session.h"
#include "common/logger.h"
#include <QAction>
#include <QKeySequence>
#include <QMenuBar>
#include <QToolBar>
#include <QStatusBar>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QMessageBox>
#include <QFileDialog>
#include <QDesktopServices>
#include <QUrl>
#include <QTextOption>
#include <QFrame>
#include <QGraphicsDropShadowEffect>
#include <QFont>
#include <thread>

namespace interview {
namespace ui {

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
    , candidate_name_("候选人")
    , min_questions_(15) {
    
    SetupUi();
    SetupMenuBar();
    SetupToolBar();
    SetupCentralWidget();
    ApplyGlobalStyle();

    // 注册全局状态机回调
    common::InterviewStateMachine::Instance().SetStateChangeCallback(
        [this](common::InterviewState old_state, common::InterviewState new_state) {
            // 在Qt主线程中更新UI
            QMetaObject::invokeMethod(this, [this, old_state, new_state]() {
                OnStateChangedFromMachine(old_state, new_state);
            }, Qt::QueuedConnection);
        }
    );

    setWindowTitle("C++ 语音面试系统");
    resize(1060, 750);

    UpdateUIState(common::InterviewStateMachine::Instance().GetState());
}

MainWindow::~MainWindow() {
    // 取消注册状态机回调
    common::InterviewStateMachine::Instance().ClearStateChangeCallback();
    
    if (session_ && session_->IsRunning()) {
        session_->Stop();
    }
    
    if (session_thread_.joinable()) {
        session_thread_.join();
    }
}

void MainWindow::SetupUi() {
    // 创建中央widget
    QWidget* central = new QWidget(this);
    setCentralWidget(central);
}

void MainWindow::SetupMenuBar() {
    QMenuBar* menuBar = new QMenuBar(this);
    setMenuBar(menuBar);
    
    // 文件菜单
    QMenu* fileMenu = menuBar->addMenu("文件(&F)");
    QAction* newAction = fileMenu->addAction("新建会话(&N)");
    newAction->setShortcut(QKeySequence::New);
    connect(newAction, &QAction::triggered, this, &MainWindow::OnNewSession);
    
    fileMenu->addSeparator();
    
    QAction* exitAction = fileMenu->addAction("退出(&X)");
    exitAction->setShortcut(QKeySequence::Quit);
    connect(exitAction, &QAction::triggered, this, &QWidget::close);
    
    // 帮助菜单
    QMenu* helpMenu = menuBar->addMenu("帮助(&H)");
    QAction* aboutAction = helpMenu->addAction("关于(&A)");
    connect(aboutAction, &QAction::triggered, this, [this]() {
        QMessageBox::about(this, "关于",
            "C++ 语音面试系统  \n\n"
            "基于AI的实时语音技术面试平台\n"
            "支持简历驱动问题生成和智能评分\n\n");
    });
}

void MainWindow::SetupToolBar() {
    QToolBar* toolbar = addToolBar("主工具栏");
    toolbar->setMovable(false);
    toolbar->setIconSize(QSize(20, 20));
    toolbar->setStyleSheet(
        "QToolBar {"
        "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        "    stop:0 #ffffff, stop:1 #f8f9fa);"
        "  border-bottom: 1px solid #e0e0e0;"
        "  padding: 6px 12px;"
        "  spacing: 10px;"
        "}"
        "QToolBar::separator {"
        "  width: 1px;"
        "  background: #e0e0e0;"
        "  margin: 4px 6px;"
        "}"
    );

    QString btnBase =
        "QPushButton {"
        "  padding: 8px 22px;"
        "  border-radius: 6px;"
        "  font-size: 13px;"
        "  font-weight: 600;"
        "  border: none;"
        "}";

    new_session_button_ = new QPushButton("  新建会话", this);
    new_session_button_->setStyleSheet(btnBase +
        "QPushButton {"
        "  background-color: #f0f4ff;"
        "  color: #3b82f6;"
        "  border: 1px solid #bfdbfe;"
        "}"
        "QPushButton:hover {"
        "  background-color: #dbeafe;"
        "}"
        "QPushButton:pressed {"
        "  background-color: #bfdbfe;"
        "}"
    );

    start_button_ = new QPushButton("  开始面试", this);
    start_button_->setStyleSheet(btnBase +
        "QPushButton {"
        "  background-color: #10b981;"
        "  color: white;"
        "}"
        "QPushButton:hover {"
        "  background-color: #059669;"
        "}"
        "QPushButton:pressed {"
        "  background-color: #047857;"
        "}"
        "QPushButton:disabled {"
        "  background-color: #d1d5db;"
        "  color: #9ca3af;"
        "}"
    );

    toolbar->addWidget(new_session_button_);
    toolbar->addSeparator();
    toolbar->addWidget(start_button_);

    connect(new_session_button_, &QPushButton::clicked, this, &MainWindow::OnNewSession);
    connect(start_button_, &QPushButton::clicked, this, &MainWindow::OnStartSession);
}

// 设置中央widget
void MainWindow::SetupCentralWidget() {
    QWidget* central = centralWidget();
    QVBoxLayout* layout = new QVBoxLayout(central);
    layout->setContentsMargins(16, 12, 16, 12);
    layout->setSpacing(12);

    // 顶部状态卡片
    QFrame* statusCard = new QFrame(this);
    statusCard->setObjectName("statusCard");
    statusCard->setStyleSheet(
        "#statusCard {"
        "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        "    stop:0 #667eea, stop:1 #764ba2);"
        "  border-radius: 10px;"
        "  padding: 0px;"
        "}"
    );
    QHBoxLayout* statusLayout = new QHBoxLayout(statusCard);
    statusLayout->setContentsMargins(18, 14, 18, 14);

    status_label_ = new QLabel("  就绪", this);
    status_label_->setStyleSheet(
        "QLabel {"
        "  color: white;"
        "  font-weight: bold;"
        "  font-size: 14px;"
        "  background: transparent;"
        "  border: none;"
        "}"
    );
    statusLayout->addWidget(status_label_);
    statusLayout->addStretch();

    // 右侧小标签
    QLabel* brandLabel = new QLabel("AI Interview", this);
    brandLabel->setStyleSheet(
        "QLabel {"
        "  color: rgba(255,255,255,0.7);"
        "  font-size: 12px;"
        "  font-style: italic;"
        "  background: transparent;"
        "  border: none;"
        "}"
    );
    statusLayout->addWidget(brandLabel);

    layout->addWidget(statusCard);

    // 消息显示区域
    message_area_ = new QTextEdit(this);
    message_area_->setReadOnly(true);
    message_area_->setLineWrapMode(QTextEdit::WidgetWidth);
    message_area_->setWordWrapMode(QTextOption::WrapAtWordBoundaryOrAnywhere);
    message_area_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    message_area_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    message_area_->setPlaceholderText("点击「新建会话」开始配置面试...");
    message_area_->setStyleSheet(
        "QTextEdit {"
        "  background-color: #fafbfc;"
        "  border: 1px solid #e5e7eb;"
        "  border-radius: 10px;"
        "  padding: 16px;"
        "  font-family: 'PingFang SC', 'Helvetica Neue', 'Microsoft YaHei', sans-serif;"
        "  font-size: 13px;"
        "  color: #1f2937;"
        "  selection-background-color: #bfdbfe;"
        "}"
        "QScrollBar:vertical {"
        "  border: none;"
        "  background: transparent;"
        "  width: 8px;"
        "  margin: 4px 2px;"
        "}"
        "QScrollBar::handle:vertical {"
        "  background: #cbd5e1;"
        "  border-radius: 4px;"
        "  min-height: 30px;"
        "}"
        "QScrollBar::handle:vertical:hover {"
        "  background: #94a3b8;"
        "}"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
        "  height: 0px;"
        "}"
        "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
        "  background: transparent;"
        "}"
    );
    layout->addWidget(message_area_, 1);

    // 底部栏：进度条
    QFrame* bottomBar = new QFrame(this);
    bottomBar->setObjectName("bottomBar");
    bottomBar->setStyleSheet(
        "#bottomBar {"
        "  background-color: #f8fafc;"
        "  border: 1px solid #e5e7eb;"
        "  border-radius: 8px;"
        "  padding: 4px;"
        "}"
    );
    QHBoxLayout* bottomLayout = new QHBoxLayout(bottomBar);
    bottomLayout->setContentsMargins(14, 8, 14, 8);

    QLabel* progressLabel = new QLabel("面试进度", this);
    progressLabel->setStyleSheet(
        "QLabel { color: #6b7280; font-size: 12px; font-weight: 600; background: transparent; border: none; }"
    );
    bottomLayout->addWidget(progressLabel);

    progress_bar_ = new QProgressBar(this);
    progress_bar_->setRange(0, 10);
    progress_bar_->setValue(0);
    progress_bar_->setTextVisible(true);
    progress_bar_->setFormat("%v / %m 题");
    progress_bar_->setMinimumHeight(22);
    progress_bar_->setStyleSheet(
        "QProgressBar {"
        "  border: none;"
        "  background-color: #e5e7eb;"
        "  border-radius: 11px;"
        "  text-align: center;"
        "  font-weight: 600;"
        "  font-size: 11px;"
        "  color: #374151;"
        "  min-width: 200px;"
        "}"
        "QProgressBar::chunk {"
        "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        "    stop:0 #10b981, stop:1 #34d399);"
        "  border-radius: 11px;"
        "}"
    );
    bottomLayout->addWidget(progress_bar_, 1);

    layout->addWidget(bottomBar);

    // 状态栏
    statusBar()->setStyleSheet(
        "QStatusBar {"
        "  background-color: #f8fafc;"
        "  color: #6b7280;"
        "  font-size: 12px;"
        "  border-top: 1px solid #e5e7eb;"
        "  padding: 2px 8px;"
        "}"
    );
    statusBar()->showMessage("就绪");
}

// 弹出配置弹窗，用户确认后把配置存下来并刷新 UI，准备好等待开始
void MainWindow::OnNewSession() {
    ConfigDialog dialog(this);
    if (dialog.exec() == QDialog::Accepted) {
        // 保存配置  
        candidate_name_ = dialog.GetCandidateName();
        resume_path_ = dialog.GetResumePath(); // 未勾选简历时返回空字符串
        min_questions_ = dialog.GetMinQuestions();
        
        // 重置 UI
        message_area_->clear(); // 清空上一次面试的对话记录          
        progress_bar_->setValue(0); // 进度归零
        progress_bar_->setMaximum(min_questions_); // 进度条满格 = 本次题目总数
        
        // 显示配置摘要到ui
        QString config_info = QString("===== 会话配置 =====\n")
                             + QString("候选人: %1\n").arg(candidate_name_);
        if (!resume_path_.isEmpty()) {
            config_info += QString("简历: %1\n").arg(resume_path_);
        }
        config_info += QString("问题数量: %1 题\n").arg(min_questions_);
        config_info += QString("========================\n");
        AppendMessage(config_info);
        
        // 解锁开始按钮    
        start_button_->setEnabled(true);
        statusBar()->showMessage("会话已配置，点击'开始面试'启动");
    }
}

// 点击"开始面试"后，在后台线程创建并启动 DialogSession，主线程只负责 UI 反馈
void MainWindow::OnStartSession() {
    if (candidate_name_.isEmpty()) {
        QMessageBox::warning(this, "警告", "请先新建会话并配置");
        return;
    }
    
    // 禁用按钮，防止重复点击
    start_button_->setEnabled(false);
    new_session_button_->setEnabled(false);
    
    // 根据是否有简历显示不同状态
    // 切换状态卡片为橙色
    QWidget* card = status_label_->parentWidget();
    if (card) card->setStyleSheet(
        "#statusCard { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #f59e0b, stop:1 #d97706); border-radius: 10px; }");
    status_label_->setStyleSheet("QLabel { font-weight: bold; font-size: 14px; background: transparent; border: none; color: white; }");

    if (!resume_path_.isEmpty()) {
        status_label_->setText("  解析简历，生成问题中...");
        AppendMessage("正在解析简历，生成问题中...\n", "#b45309");
        statusBar()->showMessage("正在解析简历，生成问题中...");
    } else {
        status_label_->setText("  生成问题中...");
        AppendMessage("正在生成问题中...\n", "#b45309");
        statusBar()->showMessage("正在生成问题中...");
    }
    
    // 启动会话线程
    session_thread_ = std::thread([this]() {
        try {
            session_ = std::make_unique<session::DialogSession>(candidate_name_.toStdString());
            
            // 设置对话内容回调
            session_->SetDialogContentCallback(
                [this](const std::string& role, const std::string& text, int question_index) {
                    // 切换到主线程更新UI
                    QMetaObject::invokeMethod(this, [this, role, text, question_index]() {
                        if (role == "interviewer") {
                            AppendMessage(QString("🎙️ 【面试官】：%1\n").arg(QString::fromStdString(text)), "#0066cc");
                            progress_bar_->setValue(question_index);
                        } else if (role == "candidate") {
                            AppendMessage(QString("👤 【候选人】：%1\n").arg(QString::fromStdString(text)), "#009688");
                        }
                    }, Qt::QueuedConnection);
                }
            );
            
            // 配置简历面试
            if (!resume_path_.isEmpty()) {
                session_->ConfigureResumeInterview(resume_path_.toStdString(), min_questions_);
            } else {
                session_->ConfigureDefaultInterview(min_questions_); 
            }
            
            // 启动会话
            session_->Start();
            
        } catch (const std::exception& e) {
            // 在主线程显示错误
            QMetaObject::invokeMethod(this, [this, error = std::string(e.what())]() {
                QMessageBox::critical(this, "错误", QString::fromStdString(error));
                AppendMessage(QString("错误: %1\n").arg(QString::fromStdString(error)), "red");
                
                // 恢复按钮状态
                start_button_->setEnabled(true);
                new_session_button_->setEnabled(true);
            }, Qt::QueuedConnection);
        }
    });
}

void MainWindow::OnStateChangedFromMachine(InterviewState old_state, InterviewState new_state) {
    UpdateUIState(new_state);
    
    QString state_text = GetStateText(new_state);
    status_label_->setText("● " + state_text);
    statusBar()->showMessage(state_text);
    
    LOG_INFO("UI State changed: {} -> {}", 
             common::InterviewStateMachine::Instance().GetStateName(old_state),
             common::InterviewStateMachine::Instance().GetStateName(new_state));
    
    // 1. 连接成功 -> 面试官说话（开场白）
    if (old_state == InterviewState::kConnecting && new_state == InterviewState::kInterviewerSpeaking) {
        AppendMessage("\n✓ 连接成功，面试开始\n", "blue");
    }
    // 2. 空闲/思考 -> 面试官说话（提问）
    else if ((old_state == InterviewState::kIdle || old_state == InterviewState::kInterviewerThinking)
             && new_state == InterviewState::kInterviewerSpeaking) {
        // AppendMessage("\n【面试官提问】\n", "blue");
    }
    // 4. 空闲 -> 候选人说话（VAD检测到说话）
    else if (old_state == InterviewState::kIdle && new_state == InterviewState::kCandidateSpeaking) {
        AppendMessage("\n【候选人回答中】\n", "green");
    }
    // 5. 候选人说话 -> 面试官思考（ASR最终结果）
    else if (old_state == InterviewState::kCandidateSpeaking && new_state == InterviewState::kInterviewerThinking) {
        AppendMessage("【回答结束，正在评估...】\n", "orange");
    }
    // 6. 会话结束
    else if (new_state == InterviewState::kSessionEnding) {
        AppendMessage("\n===== 面试即将结束 =====\n", "blue");
    }
    else if (new_state == InterviewState::kCompleted) {
        AppendMessage("\n✓ 面试已完成！报告已保存\n", "blue");
    }
    else if (new_state == InterviewState::kError) {
        AppendMessage("\n✗ 发生错误，面试中断\n", "red");
    }
}

// Qt 界面状态管理函数
void MainWindow::UpdateUIState(InterviewState state) {
    // status_label_ 现在在渐变卡片内，只需改文字颜色
    QString labelBase = "QLabel { font-weight: bold; font-size: 14px; background: transparent; border: none; ";
    // 卡片渐变根据状态切换
    auto setCard = [this](const QString& gradient) {
        QWidget* card = status_label_->parentWidget();
        if (card) card->setStyleSheet(
            QString("#statusCard { background: qlineargradient(%1); border-radius: 10px; }").arg(gradient));
    };

    switch (state) {
    case InterviewState::kIdle:
        if (session_ && session_->IsRunning()) {
            start_button_->setEnabled(false);
            new_session_button_->setEnabled(false);
            setCard("x1:0,y1:0,x2:1,y2:0, stop:0 #10b981, stop:1 #059669");
        } else {
            start_button_->setEnabled(false);
            new_session_button_->setEnabled(true);
            setCard("x1:0,y1:0,x2:1,y2:0, stop:0 #667eea, stop:1 #764ba2");
        }
        status_label_->setStyleSheet(labelBase + "color: white; }");
        break;
    case InterviewState::kConnecting:
        start_button_->setEnabled(false);
        new_session_button_->setEnabled(false);
        setCard("x1:0,y1:0,x2:1,y2:0, stop:0 #f59e0b, stop:1 #d97706");
        status_label_->setStyleSheet(labelBase + "color: white; }");
        break;
    case InterviewState::kInterviewerSpeaking:
    case InterviewState::kCandidateSpeaking:
    case InterviewState::kInterviewerThinking:
        start_button_->setEnabled(false);
        new_session_button_->setEnabled(false);
        setCard("x1:0,y1:0,x2:1,y2:0, stop:0 #10b981, stop:1 #059669");
        status_label_->setStyleSheet(labelBase + "color: white; }");
        break;
    case InterviewState::kSessionEnding:
        start_button_->setEnabled(false);
        new_session_button_->setEnabled(false);
        setCard("x1:0,y1:0,x2:1,y2:0, stop:0 #f59e0b, stop:1 #d97706");
        status_label_->setStyleSheet(labelBase + "color: white; }");
        break;
    case InterviewState::kCompleted:
        start_button_->setEnabled(false);
        new_session_button_->setEnabled(true);
        setCard("x1:0,y1:0,x2:1,y2:0, stop:0 #3b82f6, stop:1 #2563eb");
        status_label_->setStyleSheet(labelBase + "color: white; }");
        break;
    case InterviewState::kError:
        start_button_->setEnabled(false);
        new_session_button_->setEnabled(true);
        setCard("x1:0,y1:0,x2:1,y2:0, stop:0 #ef4444, stop:1 #dc2626");
        status_label_->setStyleSheet(labelBase + "color: white; }");
        break;
    default:
        break;
    }
}

QString MainWindow::GetStateText(InterviewState state) {
    return QString::fromUtf8(common::InterviewStateMachine::Instance().GetStateName(state));
}

void MainWindow::AppendMessage(const QString& text, const QString& color) {
    // 根据内容类型使用不同的气泡样式
    QString bgColor = "#ffffff";
    QString borderColor = "#e5e7eb";
    QString textColor = color.isEmpty() || color == "black" ? "#1f2937" : color;

    // 面试官消息 - 蓝色系
    if (text.contains("面试官")) {
        bgColor = "#eff6ff";
        borderColor = "#bfdbfe";
        textColor = "#1e40af";
    }
    // 候选人消息 - 绿色系
    else if (text.contains("候选人")) {
        bgColor = "#f0fdf4";
        borderColor = "#bbf7d0";
        textColor = "#166534";
    }
    // 系统消息 - 灰色
    else if (text.contains("=====") || text.contains("配置") || text.contains("连接")) {
        bgColor = "#f8fafc";
        borderColor = "#e2e8f0";
        textColor = "#475569";
    }

    QString html_text = QString(
        "<div style='"
        "  background-color: %1;"
        "  border: 1px solid %2;"
        "  border-radius: 8px;"
        "  padding: 10px 14px;"
        "  margin: 4px 0px;"
        "  color: %3;"
        "  font-size: 13px;"
        "  line-height: 1.6;"
        "'>%4</div>")
        .arg(bgColor)
        .arg(borderColor)
        .arg(textColor)
        .arg(text.toHtmlEscaped().replace("\n", "<br>"));

    message_area_->moveCursor(QTextCursor::End);
    message_area_->insertHtml(html_text);
    message_area_->moveCursor(QTextCursor::End);
    message_area_->ensureCursorVisible();
}

void MainWindow::ApplyGlobalStyle() {
    // 全局窗口背景和字体
    setStyleSheet(
        "QMainWindow {"
        "  background-color: #f1f5f9;"
        "}"
        "QMenuBar {"
        "  background-color: #ffffff;"
        "  border-bottom: 1px solid #e5e7eb;"
        "  padding: 2px 0px;"
        "  font-size: 13px;"
        "}"
        "QMenuBar::item {"
        "  padding: 6px 12px;"
        "  border-radius: 4px;"
        "}"
        "QMenuBar::item:selected {"
        "  background-color: #f0f4ff;"
        "  color: #3b82f6;"
        "}"
        "QMenu {"
        "  background-color: #ffffff;"
        "  border: 1px solid #e5e7eb;"
        "  border-radius: 8px;"
        "  padding: 4px;"
        "}"
        "QMenu::item {"
        "  padding: 8px 24px;"
        "  border-radius: 4px;"
        "}"
        "QMenu::item:selected {"
        "  background-color: #eff6ff;"
        "  color: #3b82f6;"
        "}"
        "QMenu::separator {"
        "  height: 1px;"
        "  background: #e5e7eb;"
        "  margin: 4px 8px;"
        "}"
    );
}

} // namespace ui
} // namespace interview
