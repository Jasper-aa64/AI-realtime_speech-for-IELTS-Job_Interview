#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <string>

#include "interview/interview_manager.h"

using interview::session::InterviewSession;

TEST(InterviewTest, ConstructorAndBasicGetters) {
    InterviewSession session("测试候选人");

    EXPECT_EQ(session.GetCurrentQuestionIndex(), 0);
    EXPECT_EQ(session.GetLastScore(), 0);
    EXPECT_FALSE(session.ShouldFollowUp());
    EXPECT_FALSE(session.IsComplete());
}

TEST(InterviewTest, IntroPromptShouldNotBeEmpty) {
    InterviewSession session("测试候选人");

    const std::string intro = session.GetIntroPrompt();
    EXPECT_FALSE(intro.empty());
}

TEST(InterviewTest, QuestionAccessThrowsWhenNotLoaded) {
    InterviewSession session("测试候选人");

    EXPECT_THROW(session.GetFirstQuestion(), std::runtime_error);
    EXPECT_THROW(session.GetNextQuestion(), std::runtime_error);
    EXPECT_EQ(session.GetFollowUpQuestion(), "");
}

TEST(InterviewTest, SummaryAndReportWhenNoRecords) {
    InterviewSession session("测试候选人");

    EXPECT_EQ(session.GenerateSummary(), "本次面试尚未开始，暂无总结。");

    const auto report = session.GenerateReport();
    ASSERT_TRUE(report.contains("error"));
    EXPECT_EQ(report["error"], "No interview records");
}

TEST(InterviewTest, SaveReportWritesJsonFile) {
    InterviewSession session("测试候选人");

    const std::string filename = "interview_test_report.json";
    const std::string output = session.SaveReport(filename);

    EXPECT_EQ(output, filename);
    EXPECT_TRUE(std::filesystem::exists(filename));

    std::ifstream ifs(filename);
    ASSERT_TRUE(ifs.good());
    const std::string content(
        (std::istreambuf_iterator<char>(ifs)),
        std::istreambuf_iterator<char>()
    );
    EXPECT_FALSE(content.empty());

    // 清理测试文件，避免污染工作目录
    std::filesystem::remove(filename);
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
