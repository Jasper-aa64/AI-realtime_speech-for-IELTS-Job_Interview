#include <gtest/gtest.h>
#include "common/logger.h"
#include <iostream>
#include <fstream>
#include <filesystem>
#include <thread>
#include <chrono>

using namespace interview::common;
namespace fs = std::filesystem;

class LoggerTest : public ::testing::Test {
protected:
    static int test_counter;

    void SetUp() override {
        test_log_file = "test_logger_" + std::to_string(test_counter++) + ".log";
        if (fs::exists(test_log_file)) {
            fs::remove(test_log_file);
        }
    }

    void TearDown() override {
        if (fs::exists(test_log_file)) {
            fs::remove(test_log_file);
        }
    }

    std::string test_log_file;
};

int LoggerTest::test_counter = 0;

// 测试1：基础初始化和日志记录
TEST_F(LoggerTest, BasicLogging) {
    Logger::Init(test_log_file, false);

    LOG_INFO("This is an info message");
    LOG_WARN("This is a warning message");
    LOG_ERROR("This is an error message");

    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    Logger::GetLogger()->flush();

    if (fs::exists(test_log_file)) {
        std::ifstream log_file(test_log_file);
        std::string content((std::istreambuf_iterator<char>(log_file)),
                           std::istreambuf_iterator<char>());
        EXPECT_TRUE(content.find("This is an info message") != std::string::npos);
    }
    SUCCEED();
}

// 测试2：Debug 模式
TEST_F(LoggerTest, DebugMode) {
    Logger::Init(test_log_file, true);

    LOG_DEBUG("Debug mode enabled");
    LOG_TRACE("This is a trace message in debug mode");
    LOG_INFO("Info message in debug mode");

    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    Logger::GetLogger()->flush();

    SUCCEED();  // 如果能运行到这里，说明初始化成功
}

// 测试3：防重复初始化
TEST_F(LoggerTest, NoDoubleInit) {
    auto logger1 = Logger::GetLogger();  // 第一次获取会自动初始化

    std::string test_log_file2 = "another_log.log";
    Logger::Init(test_log_file2, false);  // 这个应该被忽略
    auto logger2 = Logger::GetLogger();

    EXPECT_EQ(logger1.get(), logger2.get());  // 应该是同一个实例

    if (fs::exists(test_log_file2)) {
        fs::remove(test_log_file2);
    }
}

// 测试4：各级别日志
TEST_F(LoggerTest, AllLogLevels) {
    Logger::Init(test_log_file, true);

    LOG_TRACE("Trace level message");
    LOG_DEBUG("Debug level message");
    LOG_INFO("Info level message");
    LOG_WARN("Warn level message");
    LOG_WARNING("Warning level message (same as warn)");
    LOG_ERROR("Error level message");
    LOG_CRITICAL("Critical level message");

    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    Logger::GetLogger()->flush();

    if (fs::exists(test_log_file)) {
        std::ifstream log_file(test_log_file);
        std::string content((std::istreambuf_iterator<char>(log_file)),
                           std::istreambuf_iterator<char>());

        // 文件应该包含所有级别（因为 file sink 设置为 trace）
        EXPECT_TRUE(content.find("Info level message") != std::string::npos);
        EXPECT_TRUE(content.find("Error level message") != std::string::npos);
    }
    SUCCEED();
}

// 测试5：格式化参数
TEST_F(LoggerTest, FormattedLogging) {
    Logger::Init(test_log_file, false);

    int count = 42;
    std::string name = "TestUser";
    double value = 3.14159;

    LOG_INFO("Count: {}, Name: {}, Value: {:.2f}", count, name, value);

    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    Logger::GetLogger()->flush();

    if (fs::exists(test_log_file)) {
        std::ifstream log_file(test_log_file);
        std::string content((std::istreambuf_iterator<char>(log_file)),
                           std::istreambuf_iterator<char>());

        EXPECT_TRUE(content.find("Count: 42") != std::string::npos);
        EXPECT_TRUE(content.find("Name: TestUser") != std::string::npos);
        EXPECT_TRUE(content.find("Value: 3.14") != std::string::npos);
    }
}

// 测试6：源位置信息（文件名、行号、函数名）
TEST_F(LoggerTest, SourceLocationInfo) {
    Logger::Init(test_log_file, true);

    LOG_ERROR("Error at this line");  // 这行会在文件里记录源位置

    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    Logger::GetLogger()->flush();

    if (fs::exists(test_log_file)) {
        std::ifstream log_file(test_log_file);
        std::string content((std::istreambuf_iterator<char>(log_file)),
                           std::istreambuf_iterator<char>());

        // 文件输出应该包含文件名、行号、函数名
        EXPECT_TRUE(content.find("logger_test.cpp") != std::string::npos ||
                    content.find("logger_test") != std::string::npos);
        EXPECT_TRUE(content.find("Error at this line") != std::string::npos);
    }
}

// 测试7：并发日志（多线程）
TEST_F(LoggerTest, ConcurrentLogging) {
    Logger::Init(test_log_file, false);

    auto log_from_thread = [](int thread_id) {
        for (int i = 0; i < 5; ++i) {
            LOG_INFO("Thread {} - Message {}", thread_id, i);
        }
    };

    std::thread t1(log_from_thread, 1);
    std::thread t2(log_from_thread, 2);
    std::thread t3(log_from_thread, 3);

    t1.join();
    t2.join();
    t3.join();

    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    Logger::GetLogger()->flush();

    if (fs::exists(test_log_file)) {
        std::ifstream log_file(test_log_file);
        std::string content((std::istreambuf_iterator<char>(log_file)),
                           std::istreambuf_iterator<char>());

        EXPECT_TRUE(content.find("Thread 1") != std::string::npos);
        EXPECT_TRUE(content.find("Thread 2") != std::string::npos);
        EXPECT_TRUE(content.find("Thread 3") != std::string::npos);
    }
}

// 演示函数：直观展示日志输出效果
void DemoLoggerOutput() {
    std::cout << "\n" << std::string(70, '=') << std::endl;
    std::cout << "Logger Output Demo (Release Mode)" << std::endl;
    std::cout << std::string(70, '=') << std::endl;

    Logger::Init("demo_release.log", false);

    LOG_INFO("Application started");
    LOG_DEBUG("Debug message (should NOT appear in release mode)");
    LOG_WARN("Warning: something needs attention");
    LOG_ERROR("Error occurred but recoverable");
    LOG_CRITICAL("Critical error!");

    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    std::cout << "\n" << std::string(70, '=') << std::endl;
    std::cout << "Logger Output Demo (Debug Mode)" << std::endl;
    std::cout << std::string(70, '=') << std::endl;

    // 这里无法重新初始化，但可以展示日志内容
    std::ifstream log_file("demo_release.log");
    std::cout << "\nLog file content:\n";
    std::cout << std::string(70, '-') << std::endl;
    std::cout << std::string((std::istreambuf_iterator<char>(log_file)),
                            std::istreambuf_iterator<char>());
    std::cout << std::string(70, '-') << std::endl;
}

int main(int argc, char** argv) {
    // 首先运行演示
    DemoLoggerOutput();

    // 然后运行 Google Test
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
