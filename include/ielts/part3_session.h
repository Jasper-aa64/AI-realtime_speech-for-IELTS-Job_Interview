#pragma once
#include "ielts/question_bank.h"
#include "ielts/scorer.h"
#include <string>
#include <vector>

namespace interview { namespace services { class RealtimeClient; } }

namespace ielts {

class Part3Session {
public:
    // data_dir: path to data/ielts/ — reads prompts/p3_question_gen.md
    Part3Session(const P2Topic& p2_topic,
                 interview::services::RealtimeClient& rt_client,
                 Scorer& scorer,
                 const std::string& data_dir);

    // Generates questions via claude CLI, then runs interactive Q&A
    void Start();

    IELTSScore  GetScore()      const;
    std::string GetTranscript() const;

private:
    // Calls: claude -p "$(cat prompts/p3_question_gen.md)" -- "<theme>"
    std::vector<std::string> GenerateQuestions(const std::string& theme);
    bool ShouldFollowUp(const std::string& answer);

    P2Topic                                p2_topic_;
    interview::services::RealtimeClient&   rt_client_;
    Scorer&                                scorer_;
    std::string                            data_dir_;
    IELTSScore                             score_;
    std::string                            transcript_;
};

} // namespace ielts
