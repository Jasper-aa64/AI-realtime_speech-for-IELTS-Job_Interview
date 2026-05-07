#pragma once
#include "ielts/question_bank.h"
#include "ielts/scorer.h"
#include <string>

namespace interview { namespace services { class RealtimeClient; } }

namespace ielts {

class Part1Session {
public:
    // num_questions: how many P1 questions to ask (4–6 recommended)
    Part1Session(QuestionBank& bank,
                 interview::services::RealtimeClient& rt_client,
                 Scorer& scorer,
                 int num_questions = 5);

    // Blocks until all P1 questions (+ follow-ups) are done
    void Start();

    IELTSScore  GetScore()      const;
    std::string GetTranscript() const;  // full P1 dialogue as plain text

private:
    bool ShouldFollowUp(const std::string& transcript);
    std::string GetFollowUpQuestion();

    QuestionBank&                          bank_;
    interview::services::RealtimeClient&   rt_client_;
    Scorer&                                scorer_;
    int                                    num_questions_;
    IELTSScore                             score_;
    std::string                            transcript_;
};

} // namespace ielts
