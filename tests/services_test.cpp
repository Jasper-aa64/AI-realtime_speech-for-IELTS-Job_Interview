#include <gtest/gtest.h>
#include "services/audio_manager.h"
#include "services/llm_client.h"
#include "services/pdf_parser.h"
#include "services/realtime_client.h"
#include "common/config.h"
#include "common/logger.h"

using namespace interview::services;

// 测试AudioDeviceManager基础功能
TEST(ServicesTest, AudioDeviceManagerConstruction) {
    // 使用默认配置
    auto& config = interview::common::Config::Instance();

    // 测试构造函数不会抛出异常
    EXPECT_NO_THROW({
        AudioDeviceManager manager(config.input_audio_config, config.output_audio_config);
    });

    // 测试清理方法
    {
        AudioDeviceManager manager(config.input_audio_config, config.output_audio_config);
        EXPECT_NO_THROW(manager.Cleanup());
    }
}

// 测试LLMClient基础功能
TEST(ServicesTest, LLMClientConstruction) {
    EXPECT_NO_THROW({
        LLMClient client;
    });
}

// 测试PDFParser基础功能
TEST(ServicesTest, PDFParserConstruction) {
    EXPECT_NO_THROW({
        PDFParser parser;
    });
}

// 测试PDFParser文件验证
TEST(ServicesTest, PDFParserFileValidation) {
    PDFParser parser;

    // 测试不存在的文件
    EXPECT_FALSE(parser.IsValidPDF("/nonexistent/file.pdf"));

    // 测试空路径
    EXPECT_FALSE(parser.IsValidPDF(""));

    // 注意：无法测试有效PDF文件，因为测试环境可能没有PDF文件
    // 可以创建一个临时PDF文件进行测试，但这里跳过
}

// 测试RealtimeClient基础功能
TEST(ServicesTest, RealtimeClientConstruction) {
    std::map<std::string, std::string> headers = {
        {"X-Test-Header", "test-value"}
    };

    EXPECT_NO_THROW({
        RealtimeClient client("wss://example.com/test", headers);
    });
}

// 测试RealtimeClient回调设置
TEST(ServicesTest, RealtimeClientCallback) {
    std::map<std::string, std::string> headers = {
        {"X-Test-Header", "test-value"}
    };

    RealtimeClient client("wss://example.com/test", headers);

    bool callback_called = false;
    auto callback = [&callback_called](const interview::common::ParsedResponse& resp) {
        callback_called = true;
        (void)resp;
    };

    EXPECT_NO_THROW(client.SetResponseCallback(callback));

    // 注意：回调只在线程中调用，这里不测试实际调用
}

// 测试RealtimeClient关闭未连接的客户端
TEST(ServicesTest, RealtimeClientCloseWithoutConnect) {
    std::map<std::string, std::string> headers = {
        {"X-Test-Header", "test-value"}
    };

    RealtimeClient client("wss://example.com/test", headers);

    // 未连接时关闭应该不会抛出异常
    EXPECT_NO_THROW(client.Close());
}

// 测试Config单例
TEST(ServicesTest, ConfigSingleton) {
    auto& config1 = interview::common::Config::Instance();
    auto& config2 = interview::common::Config::Instance();

    // 应该是同一个实例
    EXPECT_EQ(&config1, &config2);

    // 测试默认配置值
    EXPECT_EQ(config1.input_audio_config.sample_rate, 16000);
    EXPECT_EQ(config1.output_audio_config.sample_rate, 24000);
    EXPECT_EQ(config1.llm_config.timeout_seconds, 60);
}

// 测试Logger初始化
TEST(ServicesTest, LoggerInitialization) {
    // 日志系统应该已经初始化，记录一条测试日志
    EXPECT_NO_THROW(LOG_INFO("Test log message from unit test"));
}

// 主函数 - Google Test会自动提供，但我们也可以自定义
int main(int argc, char **argv) {
    // 初始化Google Test
    ::testing::InitGoogleTest(&argc, argv);

    // 可选：设置日志级别，避免测试输出过多
    // interview::common::Logger::SetLevel(interview::common::LogLevel::WARNING);

    return RUN_ALL_TESTS();
}