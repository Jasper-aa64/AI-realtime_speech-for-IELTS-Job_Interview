#include "ielts/part1_session.h"

#include "common/logger.h"
#include "ielts/realtime_speech_capture.h"
#include "services/realtime_client.h"
#include <algorithm>
#include <cctype>
#include <iostream>
#include <iterator>
#include <sstream>
#include <vector>

namespace ielts {

namespace {

std::string ReadAnswerFromTerminal(const std::string& prompt) {
    std::cout << prompt << std::endl;
    std::cout << "> ";
    std::string answer;
    std::getline(std::cin, answer);
    return answer;
}

std::string CapturePart1AnswerOrFallback(interview::services::RealtimeClient& client,
                                         const std::string& fallback_prompt) {
    RealtimeCaptureOptions options;
    options.max_seconds = 75;
    options.stop_on_first_final = true;
    options.allow_enter_stop = true;
    options.record_audio_without_realtime = false;
    options.status_label = "Listening for answer";

    const auto capture = CaptureSpeechWithRealtime(client, options);
    if (capture.used_realtime_stt) {
        std::cout << "\033[2mTranscript:\033[0m " << capture.transcript << "\n";
        return capture.transcript;
    }

    if (!capture.fallback_reason.empty()) {
        LOG_WARNING("P1 realtime STT unavailable, using terminal transcript: {}", capture.fallback_reason);
    }
    return ReadAnswerFromTerminal(fallback_prompt);
}

int WordCount(const std::string& text) {
    std::istringstream input(text);
    return static_cast<int>(std::distance(std::istream_iterator<std::string>(input), std::istream_iterator<std::string>()));
}

std::string Lowercase(std::string text) {
    std::transform(text.begin(), text.end(), text.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return text;
}

void SafeSpeak(interview::services::RealtimeClient& client, const std::string& text) {
    try {
        client.SendTextQuery(text);
    } catch (const std::exception& e) {
        LOG_WARNING("IELTS TTS prompt failed, continuing with terminal text: {}", e.what());
    }
}

} // namespace

Part1Session::Part1Session(QuestionBank& bank,
                           interview::services::RealtimeClient& rt_client,
                           Scorer& scorer,
                           int num_questions)
    : bank_(bank)
    , rt_client_(rt_client)
    , scorer_(scorer)
    , num_questions_(num_questions) {}

void Part1Session::Start() {
    transcript_.clear();
    const auto questions = bank_.SampleP1Questions(num_questions_);

    std::cout << "\n\033[1;36mIELTS Speaking - Part 1\033[0m\n";
    std::cout << "Answer each question in English. Realtime STT will capture your speech when available.\n";
    std::cout << "Press Enter to stop early or type the transcript if realtime is unavailable.\n\n";

    int index = 1;
    for (const auto& item : questions) {
        const std::string question = "Part 1 question " + std::to_string(index) + ": " + item.question;
        std::cout << "\033[1;33m[" << item.topic << "] Examiner:\033[0m " << item.question << "\n";
        SafeSpeak(rt_client_, question);

        const std::string answer = CapturePart1AnswerOrFallback(rt_client_, "Candidate answer transcript:");
        transcript_ += "Examiner: " + item.question + "\nCandidate: " + answer + "\n";

        if (ShouldFollowUp(answer)) {
            const std::string follow_up = GetFollowUpQuestion();
            std::cout << "\033[1;33mFollow-up:\033[0m " << follow_up << "\n";
            SafeSpeak(rt_client_, follow_up);

            const std::string follow_answer = CapturePart1AnswerOrFallback(rt_client_, "Candidate follow-up answer transcript:");
            transcript_ += "Examiner: " + follow_up + "\nCandidate: " + follow_answer + "\n";
        }
        ++index;
    }

    score_ = scorer_.Score(transcript_);
}

IELTSScore Part1Session::GetScore() const {
    return score_;
}

std::string Part1Session::GetTranscript() const {
    return transcript_;
}

bool Part1Session::ShouldFollowUp(const std::string& transcript) {
    const std::string text = Lowercase(transcript);
    const bool short_answer = WordCount(text) < 30;
    const bool no_reason = text.find("because") == std::string::npos &&
                           text.find("why") == std::string::npos &&
                           text.find("reason") == std::string::npos &&
                           text.find("so ") == std::string::npos;
    return short_answer || no_reason;
}

std::string Part1Session::GetFollowUpQuestion() {
    return "Could you tell me more about that and explain why?";
}

} // namespace ielts
