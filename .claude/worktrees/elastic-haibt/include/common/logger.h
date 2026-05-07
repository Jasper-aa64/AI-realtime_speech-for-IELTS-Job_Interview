/**
 * @file logger.h
 * @brief 日志系统模块
 *
 * 本文件定义了基于spdlog的日志封装类。
 * 提供统一的日志接口，支持多级别日志、彩色输出、文件记录等功能。
 *
 * 核心功能：
 * 1. 多级别日志（TRACE/DEBUG/INFO/WARN/ERROR/CRITICAL）
 * 2. 彩色控制台输出（便于区分日志级别）
 * 3. 文件持久化（所有日志写入文件）
 * 4. 格式化输出（使用spdlog的fmt格式化语法）
 * 5. 调试模式切换（开发/生产环境不同日志级别）
 *
 * 依赖库：
 * - spdlog: 高性能C++日志库
 *
 * 架构设计：
 * - 单例模式管理全局日志实例
 * - 支持多个sink（控制台+文件）
 * - 宏定义简化日志调用
 * - 支持spdlog的fmt格式化语法
 *
 * 使用方式：
 * @code
 * // 初始化日志系统
 * Logger::Init("app.log", true);  // debug模式
 *
 * // 使用宏记录日志
 * LOG_INFO("Application started");
 * LOG_DEBUG("Processing item {}/{}", i, total);
 * LOG_ERROR("Failed to connect: {}", error_msg);
 * @endcode
 */

#pragma once

#include <spdlog/spdlog.h>
#include <spdlog/sinks/stdout_color_sinks.h>
#include <spdlog/sinks/basic_file_sink.h>
#include <memory>

namespace interview {
namespace common {

/**
 * @brief 日志管理类（单例）
 *
 * 封装spdlog日志库，提供统一的日志接口。
 *
 * 功能特性：
 * 1. 双sink设计：控制台（彩色）+ 文件（完整）
 * 2. 级别控制：logger全局TRACE，由各sink分别过滤（控制台debug/info，文件trace）
 * 3. 自动刷新：WARN及以上立即落盘 + 每秒周期flush
 * 4. 格式化：支持fmt库格式化语法
 *
 * 日志级别说明：
 * - TRACE: 非常详细的调试信息，通常不启用
 * - DEBUG: 调试信息，开发环境启用
 * - INFO: 一般信息，记录程序运行状态
 * - WARN: 警告信息，不影响运行但需要注意
 * - ERROR: 错误信息，功能失败但程序可继续
 * - CRITICAL: 严重错误，程序可能崩溃
 *
 * 输出格式：
 * - 控制台(release): [14:30:25.123] [INFO] 消息内容
 * - 控制台(debug):   [14:30:25.123] [INFO] [t:12345] [main.cpp:42] 消息内容
 * - 文件:            [2025-01-15 14:30:25.123] [info] [t:12345] [main.cpp:42 main] 消息内容
 */
class Logger {
public:
    /**
     * @brief 初始化日志系统
     *
     * 创建日志实例，配置sink和格式。
     * 应在程序启动时调用一次。
     *
     * Sink配置：
     * 1. 控制台sink（彩色）：
     *    - 日志级别：DEBUG（调试模式）或INFO（生产模式）
     *    - debug格式：[时:分:秒] [级别] [线程] [文件:行号] 消息
     *    - release格式：[时:分:秒] [级别] 消息
     *
     * 2. 文件sink：
     *    - 日志级别：TRACE（记录所有）
     *    - 格式：[日期时间] [级别] [线程] [文件:行号 函数名] 消息
     *    - 追加模式：不覆盖原有日志
     *
     * 注意：重复调用 Init() 会被忽略（防止重复注册sink）
     *
     * @param log_file 日志文件路径，默认"interview.log"
     * @param debug_mode 是否启用调试模式，默认false
     */
    static void Init(const std::string& log_file = "interview.log", bool debug_mode = false);

    /**
     * @brief 获取日志实例
     *
     * 返回全局单例日志实例。
     * 如果未初始化，会自动调用Init()使用默认配置。
     *
     * @return spdlog日志实例的共享指针
     */
    static std::shared_ptr<spdlog::logger>& GetLogger();

private:
    static std::shared_ptr<spdlog::logger> logger_;  ///< 全局日志实例（单例）
};

// ========== 便捷日志宏 ==========
// 使用 SPDLOG_LOGGER_CALL 自动携带 __FILE__ / __LINE__ / __FUNCTION__
// 使得 pattern 中的 %s / %# / %! 能正确输出源位置
// 使用示例：LOG_INFO("User {} logged in", username);

#define LOG_TRACE(...)    SPDLOG_LOGGER_CALL(::interview::common::Logger::GetLogger().get(), spdlog::level::trace, __VA_ARGS__)
#define LOG_DEBUG(...)    SPDLOG_LOGGER_CALL(::interview::common::Logger::GetLogger().get(), spdlog::level::debug, __VA_ARGS__)
#define LOG_INFO(...)     SPDLOG_LOGGER_CALL(::interview::common::Logger::GetLogger().get(), spdlog::level::info, __VA_ARGS__)
#define LOG_WARN(...)     SPDLOG_LOGGER_CALL(::interview::common::Logger::GetLogger().get(), spdlog::level::warn, __VA_ARGS__)
#define LOG_WARNING(...)  SPDLOG_LOGGER_CALL(::interview::common::Logger::GetLogger().get(), spdlog::level::warn, __VA_ARGS__)
#define LOG_ERROR(...)    SPDLOG_LOGGER_CALL(::interview::common::Logger::GetLogger().get(), spdlog::level::err, __VA_ARGS__)
#define LOG_CRITICAL(...) SPDLOG_LOGGER_CALL(::interview::common::Logger::GetLogger().get(), spdlog::level::critical, __VA_ARGS__)

} // namespace common 
} // namespace interview
