#pragma once
#include "ielts/question_bank.h"
#include "ielts/scorer.h"
#include <string>

namespace interview { namespace services { class RealtimeClient; } }

namespace ielts {

class Part2Session {
public:
    // prep_seconds: preparation time (default 60s)
    // speak_seconds: max speaking time (default 120s)
    Part2Session(QuestionBank& bank,
                 interview::services::RealtimeClient& rt_client,
                 Scorer& scorer,
                 const std::string& reports_dir,
                 int prep_seconds  = 60,
                 int speak_seconds = 120);

    // Displays cue card → countdown → records speech → scores
    void Start();

    IELTSScore  GetScore()         const;
    P2Topic     GetTopic()         const;   // passed to Part3Session
    std::string GetTranscript()    const;
    int         GetActualDuration() const;  // seconds actually spoken

private:
    void ShowCueCard(const P2Topic& topic) const;
    void RunCountdown(int seconds);           // prep timer with ENTER skip
    void RecordSpeech(int max_seconds);       // speech timer with ENTER stop

    QuestionBank&                          bank_;
    interview::services::RealtimeClient&   rt_client_;
    Scorer&                                scorer_;
    std::string                            reports_dir_;
    int                                    prep_seconds_;
    int                                    speak_seconds_;

    P2Topic     topic_;
    IELTSScore  score_;
    std::string transcript_;
    int         actual_duration_ = 0;
};

} // namespace ielts
