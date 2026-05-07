/**
 * @file main.cpp
 * @brief C++语音面试系统主程序入口
 *
 * 本文件实现了程序的main函数，负责：
 * 1. 命令行参数解析
 * 2. 日志系统初始化
 * 3. 配置LLM API参数
 * 4. 创建和启动对话会话
 * 5. 信号处理（Ctrl+C优雅退出）
 * 6. 错误处理和资源清理
 *
 * 程序流程：
 * 1. 解析命令行参数（候选人姓名、简历路径、LLM配置等）
 * 2. 初始化日志系统
 * 3. 应用LLM配置（URL、API Key、Model等）
 * 4. 创建DialogSession实例
 * 5. 配置简历驱动面试（如果提供简历）
 * 6. 启用LLM评分
 * 7. 注册信号处理器（优雅退出）
 * 8. 启动对话会话
 * 9. 等待会话结束
 * 10. 保存面试报告
 */

#include <iostream>
#include <csignal>
#include <thread>
#include "interview/dialog_session.h"
#include "common/config.h"
#include "common/logger.h"

#ifdef _WIN32
#include <windows.h>
#endif

using namespace interview;

// 全局会话指针用于信号处理
// 注意：使用全局变量是为了在信号处理器中能访问会话对象
// 信号处理器不能接受额外参数，所以需要全局变量
static session::DialogSession* g_session = nullptr;

/**
 * @brief 信号处理器函数
 *
 * 处理SIGINT（Ctrl+C）和SIGTERM信号，优雅地停止会话。
 *
 * @param signal 信号编号
 */
void SignalHandler(int signal) {
    std::cout << "\nReceived signal " << signal << ", stopping..." << std::endl;
    if (g_session) {
        g_session->Stop();  // 优雅停止会话（保存报告、关闭连接）
    }
}

/**
 * @brief C++语音面试系统主程序
 *
 * 程序入口点，解析命令行参数并启动语音面试会话。
 *
 * @param argc 命令行参数数量
 * @param argv 命令行参数数组
 * @return 0=成功，1=失败
 */
int main(int argc, char* argv[]) {
#ifdef _WIN32
    // Windows平台特定初始化：设置控制台为UTF-8编码以正确显示中文
    SetConsoleOutputCP(CP_UTF8);
    setvbuf(stdout, nullptr, _IOFBF, 1000);
#endif

    // ========== 命令行参数解析 ==========
    std::string config_file_path;
    std::string candidate_name = "候选人";
    std::string resume_pdf_path;
    int min_questions = 15;
    std::string llm_api_url;
    std::string llm_api_key;
    std::string llm_model;
    float llm_temperature = -1.0f;
    bool debug_mode = false;

    auto print_usage = []() {
        std::cout
            << "Usage:\n"
            << "  CppInterviewSystem --config-file <path> [options]\n\n"
            << "Options:\n"
            << "  -c, --candidate <name>\n"
            << "  -r, --resume <pdf_path>\n"
            << "  -q, --questions <5-100>\n"
            << "      --api-url <url>\n"
            << "      --api-key <key>\n"
            << "  -m, --model <model>\n"
            << "  -t, --temperature <0.0-2.0>\n"
            << "  -d, --debug\n";
    };

    try {
        for (int i = 1; i < argc; ++i) {
            std::string arg = argv[i];
            auto require_next = [&](const std::string& name) -> std::string {
                if (i + 1 >= argc) {
                    throw std::runtime_error("Missing value for argument: " + name);
                }
                return argv[++i];
            };

            if (arg == "--config-file") {
                config_file_path = require_next(arg);
            } else if (arg == "-c" || arg == "--candidate") {
                candidate_name = require_next(arg);
            } else if (arg == "-r" || arg == "--resume") {
                resume_pdf_path = require_next(arg);
            } else if (arg == "-q" || arg == "--questions") {
                min_questions = std::stoi(require_next(arg));
            } else if (arg == "--api-url") {
                llm_api_url = require_next(arg);
            } else if (arg == "--api-key") {
                llm_api_key = require_next(arg);
            } else if (arg == "-m" || arg == "--model") {
                llm_model = require_next(arg);
            } else if (arg == "-t" || arg == "--temperature") {
                llm_temperature = std::stof(require_next(arg));
            } else if (arg == "-d" || arg == "--debug") {
                debug_mode = true;
            } else if (arg == "-h" || arg == "--help") {
                print_usage();
                return 0;
            } else {
                throw std::runtime_error("Unknown argument: " + arg);
            }
        }
    } catch (const std::exception& e) {
        std::cerr << "Argument parse error: " << e.what() << std::endl;
        print_usage();
        return 1;
    }

    if (config_file_path.empty()) {
        std::cerr << "Error: --config-file is required" << std::endl;
        print_usage();
        return 1;
    }
    if (min_questions < 5 || min_questions > 100) {
        std::cerr << "Error: --questions must be in range [5, 100]" << std::endl;
        return 1;
    }
    if (llm_temperature != -1.0f && (llm_temperature < 0.0f || llm_temperature > 2.0f)) {
        std::cerr << "Error: --temperature must be in range [0.0, 2.0]" << std::endl;
        return 1;
    }

    // ========== 加载配置文件 ==========
    try {
        common::Config::Instance().LoadFromFile(config_file_path);
    } catch (const std::exception& e) {
        std::cerr << "Failed to load configuration: " << e.what() << std::endl;
        return 1;
    }

    // ========== 初始化日志系统 ==========
    // 必须在所有其他操作之前初始化日志
    common::Logger::Init("interview.log", debug_mode);

    LOG_INFO("========================================");
    LOG_INFO("C++ Technical Interview System v1.0");
    LOG_INFO("========================================");

    // ========== 配置LLM参数 ==========
    // 如果用户提供了LLM配置参数，覆盖Config中的默认值
    if (!llm_api_url.empty() || !llm_api_key.empty() || !llm_model.empty() || llm_temperature >= 0) {
        auto& cfg = common::Config::Instance().llm_config;
        if (!llm_api_url.empty()) {
            cfg.api_url = llm_api_url;
            LOG_INFO("LLM API URL: {}", cfg.api_url);
        }
        if (!llm_api_key.empty()) {
            cfg.api_key = llm_api_key;
            LOG_INFO("LLM API Key: {}...", cfg.api_key.substr(0, 8));  // 只打印前8个字符（安全）
        }
        if (!llm_model.empty()) {
            cfg.model = llm_model;
            LOG_INFO("LLM Model: {}", cfg.model);
        }
        if (llm_temperature >= 0) {
            cfg.temperature = llm_temperature;
            LOG_INFO("LLM Temperature: {}", cfg.temperature);
        }
    }

    // ========== 启动语音面试 ==========
    try {
        LOG_INFO("========================================");
        LOG_INFO("Starting Voice Interview");
        LOG_INFO("========================================");
        LOG_INFO("Candidate: {}", candidate_name);
        LOG_INFO("");
        LOG_INFO("Please prepare your microphone and speaker.");
        LOG_INFO("The interview will begin in 3 seconds...");
        LOG_INFO("");

        // 延迟3秒，给用户准备时间
        std::this_thread::sleep_for(common::timing::INTERVIEW_START_DELAY);

        // 创建对话会话
        session::DialogSession session(candidate_name);
        g_session = &session;  // 保存到全局变量供信号处理器使用

        // 如果提供了简历，配置简历驱动面试
        if (!resume_pdf_path.empty()) {
            LOG_INFO("Loading resume from: {}", resume_pdf_path);
            try {
                // 解析PDF并生成针对性问题
                session.ConfigureResumeInterview(resume_pdf_path, min_questions);
                LOG_INFO("Resume-driven interview configured");
            } catch (const std::exception& e) {
                LOG_ERROR("Failed to load resume: {}", e.what());
                throw;  // 简历加载失败是致命错误，终止程序
            }
        }

        // 注册信号处理器，支持Ctrl+C优雅退出
        std::signal(SIGINT, SignalHandler);
        std::signal(SIGTERM, SignalHandler);

        // 启动会话（连接服务器、初始化音频、发送开场白）
        LOG_INFO("Starting session...");
        try {
            session.Start();
        } catch (const std::exception& e) {
            LOG_ERROR("Failed to start session: {}", e.what());
            throw;  // 启动失败是致命错误
        }

        // 主循环：等待会话结束
        LOG_INFO("");
        LOG_INFO("Interview session is running...");
        LOG_INFO("Press Ctrl+C to stop.");
        LOG_INFO("");

        // 轮询检查会话状态（每100ms检查一次）
        while (session.IsRunning()) {
            std::this_thread::sleep_for(common::timing::MAIN_LOOP_INTERVAL);
        }

        // 会话正常结束
        LOG_INFO("========================================");
        LOG_INFO("Interview Completed!");
        LOG_INFO("========================================");
        LOG_INFO("Thank you for participating!");
        LOG_INFO("The interview report has been saved.");

    } catch (const std::exception& e) {
        // 捕获所有异常，记录日志并返回错误码
        LOG_ERROR("Fatal error: {}", e.what());
        return 1;
    }

    // 清理全局变量
    g_session = nullptr;
    return 0;
}
