#include <gtest/gtest.h>

#include "common/logger.h"
#include "ielts/question_bank.h"
#include "ielts/scorer.h"

#include <string>

namespace {

std::string DataDir() {
    return std::string(PROJECT_ROOT) + "/data/ielts";
}

} // namespace

TEST(IELTSDataTest, LoadsBundledQuestionBank) {
    interview::common::Logger::Init("ielts_data_test.log", false);

    ielts::QuestionBank bank;
    ASSERT_NO_THROW(bank.LoadPart1(DataDir()));
    ASSERT_NO_THROW(bank.LoadPart2(DataDir()));

    EXPECT_GE(bank.Part1Count(), 15);
    EXPECT_GE(bank.Part2Count(), 3);

    const auto p1_questions = bank.SampleP1Questions(5);
    ASSERT_EQ(p1_questions.size(), 5u);
    for (const auto& item : p1_questions) {
        EXPECT_FALSE(item.topic.empty());
        EXPECT_FALSE(item.question.empty());
    }

    const auto p2_topic = bank.SampleP2Topic();
    EXPECT_FALSE(p2_topic.title.empty());
    EXPECT_GE(p2_topic.bullets.size(), 3u);
    EXPECT_FALSE(p2_topic.p3_theme.empty());
}

TEST(IELTSDataTest, LoadsScorerPrompt) {
    EXPECT_NO_THROW(ielts::Scorer scorer(DataDir()));
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
