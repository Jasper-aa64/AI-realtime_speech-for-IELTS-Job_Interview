#pragma once
#include <string>
#include <vector>

namespace ielts {

struct P1Question {
    std::string topic;
    std::string question;
};

struct P2Topic {
    std::string title;
    std::vector<std::string> bullets;
    std::string rounding;
    std::string p3_theme;
};

class QuestionBank {
public:
    void LoadPart1(const std::string& data_dir);
    void LoadPart2(const std::string& data_dir);

    // Sample n P1 questions randomly across all loaded topics
    std::vector<P1Question> SampleP1Questions(int n = 5) const;
    // Sample one P2 topic randomly
    P2Topic SampleP2Topic() const;

    int Part1Count() const;
    int Part2Count() const;

private:
    std::vector<P1Question> p1_questions_;
    std::vector<P2Topic>    p2_topics_;
};

} // namespace ielts
