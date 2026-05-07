#include "common/logger.h"

#include <spdlog/spdlog.h>
#include <spdlog/sinks/stdout_color_sinks.h>
#include <spdlog/sinks/basic_file_sink.h>

#include <chrono>
#include <iostream>
#include <memory>
#include <vector>

namespace interview {
namespace common {

std::shared_ptr<spdlog::logger> Logger::logger_ = nullptr;

void Logger::Init(const std::string& log_file, bool debug_mode) {
    try {
        if (logger_) return;

        std::vector<spdlog::sink_ptr> sinks;
        sinks.reserve(2);

        // 控制台 sink：debug 模式带线程+源位置，release 模式简洁
        auto console_sink = std::make_shared<spdlog::sinks::stdout_color_sink_mt>();
        console_sink->set_level(debug_mode ? spdlog::level::debug : spdlog::level::info);
        if (debug_mode) {
            console_sink->set_pattern("[%H:%M:%S.%e] [%^%l%$] [t:%t] [%s:%#] %v");
        } else {
            console_sink->set_pattern("[%H:%M:%S.%e] [%^%l%$] %v");
        }
        sinks.push_back(console_sink);

        // 文件 sink：全量记录，含日期、线程、源位置、函数名
        auto file_sink = std::make_shared<spdlog::sinks::basic_file_sink_mt>(log_file, /*truncate=*/false);
        file_sink->set_level(spdlog::level::trace);
        file_sink->set_pattern("[%Y-%m-%d %H:%M:%S.%e] [%l] [t:%t] [%s:%# %!] %v");
        sinks.push_back(file_sink);

        logger_ = std::make_shared<spdlog::logger>("interview", sinks.begin(), sinks.end());

        // 全局级别 trace，让各 sink 各自过滤
        logger_->set_level(spdlog::level::trace);

        logger_->flush_on(spdlog::level::warn);
        spdlog::flush_every(std::chrono::seconds(1));

        spdlog::set_default_logger(logger_);

        SPDLOG_LOGGER_INFO(logger_, "Logger initialized. debug_mode={}, log_file={}", debug_mode, log_file);
    }
    catch (const spdlog::spdlog_ex& ex) {
        std::cerr << "Log initialization failed: " << ex.what() << std::endl;
    }
}

std::shared_ptr<spdlog::logger>& Logger::GetLogger() {
    if (!logger_) {
        Init();
    }
    return logger_;
}

} // namespace common
} // namespace interview
