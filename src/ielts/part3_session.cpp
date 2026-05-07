#include "ielts/part3_session.h"

#include "common/logger.h"
#include "ielts/realtime_speech_capture.h"
#include "services/realtime_client.h"
#include <algorithm>
#include <array>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <sstream>
#include <stdexcept>
#include <sys/wait.h>
#include <unistd.h>
#include <nlohmann/json.hpp>

namespace ielts {

namespace {

std::string ReadTextFile(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) {
        throw std::runtime_error("Failed to open prompt file: " + path.string());
    }
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return buffer.str();
}

std::string ShellQuote(const std::string& value) {
    std::string quoted = "'";
    for (char c : value) {
        if (c == '\'') {
            quoted += "'\\''";
        } else {
            quoted += c;
        }
    }
    quoted += "'";
    return quoted;
}

std::string Trim(std::string value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) {
        return "";
    }
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

std::string ClaudeBinary() {
    const char* home = std::getenv("HOME");
    if (home != nullptr) {
        const auto local_claude = std::filesystem::path(home) / ".local/bin/claude";
        if (std::filesystem::exists(local_claude)) {
            return local_claude.string();
        }
    }
    return "claude";
}

std::string RunClaudeWithPromptFile(const std::filesystem::path& prompt_path) {
    const std::string command =
        ShellQuote(ClaudeBinary()) +
        " --print --output-format text --input-format text --allowedTools none < " +
        ShellQuote(prompt_path.string()) +
        " 2>/dev/null";

    std::array<char, 4096> buffer{};
    std::string result;
    FILE* pipe = ::popen(command.c_str(), "r");
    if (!pipe) {
        throw std::runtime_error("Failed to start claude CLI");
    }
    while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe) != nullptr) {
        result += buffer.data();
    }
    const int status = ::pclose(pipe);
    if (status == -1 || !WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        throw std::runtime_error("claude CLI exited with non-zero status");
    }
    if (result.empty()) {
        throw std::runtime_error("claude CLI returned empty output");
    }
    return result;
}

std::string ExtractJsonArray(const std::string& text) {
    const auto begin = text.find('[');
    const auto end = text.rfind(']');
    if (begin == std::string::npos || end == std::string::npos || end < begin) {
        throw std::runtime_error("Claude question output did not contain a JSON array");
    }
    return text.substr(begin, end - begin + 1);
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

Part3Session::Part3Session(const P2Topic& p2_topic,
                           interview::services::RealtimeClient& rt_client,
                           Scorer& scorer,
                           const std::string& data_dir)
    : p2_topic_(p2_topic)
    , rt_client_(rt_client)
    , scorer_(scorer)
    , data_dir_(data_dir) {}

void Part3Session::Start() {
    transcript_.clear();

    std::cout << "\n\033[1;36mIELTS Speaking - Part 3\033[0m\n";
    auto questions = GenerateQuestions(p2_topic_.p3_theme);
    for (const auto& question : questions) {
        std::cout << "\033[1;33mExaminer:\033[0m " << question << "\n";
        SafeSpeak(rt_client_, question);
        const std::string answer = CaptureAnswerOrFallback(rt_client_, "Candidate answer transcript:");
        transcript_ += "Examiner: " + question + "\nCandidate: " + answer + "\n";

        if (ShouldFollowUp(answer)) {
            const std::string follow_up = GetFollowUpQuestion(question, answer);
            std::cout << "\033[1;33mFollow-up:\033[0m " << follow_up << "\n";
            SafeSpeak(rt_client_, follow_up);
            const std::string follow_answer = CaptureAnswerOrFallback(rt_client_, "Candidate follow-up answer transcript:");
            transcript_ += "Examiner: " + follow_up + "\nCandidate: " + follow_answer + "\n";
        }
    }

    score_ = scorer_.Score(transcript_);
}

IELTSScore Part3Session::GetScore() const {
    return score_;
}

std::string Part3Session::GetTranscript() const {
    return transcript_;
}

std::vector<std::string> Part3Session::GenerateQuestions(const std::string& theme) {
    try {
        const auto prompt_path = std::filesystem::path(data_dir_) / "prompts" / "p3_question_gen.md";
        const auto prompt = ReadTextFile(prompt_path) + "\n" + theme + "\nP2 Topic: " + p2_topic_.title + "\n";
        const auto temp_path = std::filesystem::temp_directory_path() /
            ("ielts_p3_" + std::to_string(::getpid()) + ".txt");
        {
            std::ofstream output(temp_path);
            if (!output) {
                throw std::runtime_error("Failed to write temporary Claude prompt");
            }
            output << prompt;
        }

        std::string result;
        try {
            result = RunClaudeWithPromptFile(temp_path);
        } catch (...) {
            std::filesystem::remove(temp_path);
            throw;
        }
        std::filesystem::remove(temp_path);

        const auto parsed = nlohmann::json::parse(ExtractJsonArray(result));
        std::vector<std::string> questions;
        for (const auto& item : parsed) {
            if (item.is_string()) {
                questions.push_back(item.get<std::string>());
            }
        }
        if (!questions.empty()) {
            return questions;
        }
    } catch (const std::exception& e) {
        LOG_WARNING("P3 question generation failed, using fallback questions: {}", e.what());
    }

    return {
        "How common is this topic in your country?",
        "Why do people have different opinions about this issue?",
        "How has this area changed compared with the past?",
        "What are the advantages and disadvantages for society?",
        "How do you think this topic will develop in the future?"
    };
}

std::string Part3Session::GetFollowUpQuestion(const std::string& question,
                                               const std::string& answer) {
    static const std::vector<std::string> kFallbacks = {
        "Could you explain your reasoning in more detail?",
        "What makes you think that?",
        "Can you give a concrete example from your own experience?",
        "How does that compare to the situation in other countries?",
        "Do you think this will change in the future? Why?"
    };
    static size_t fallback_index = 0;

    try {
        const std::string prompt =
            "You are an IELTS examiner. The candidate gave a short/thin answer to the question below.\n"
            "Generate ONE natural follow-up probe question in one sentence.\n"
            "Question: " + question + "\n"
            "Candidate answer: " + answer + "\n"
            "Output ONLY the question, no explanation.\n";
        const auto temp_path = std::filesystem::temp_directory_path() /
            ("ielts_p3_followup_" + std::to_string(::getpid()) + ".txt");
        {
            std::ofstream output(temp_path);
            if (!output) {
                throw std::runtime_error("Failed to write temporary Claude follow-up prompt");
            }
            output << prompt;
        }

        std::string result;
        try {
            result = Trim(RunClaudeWithPromptFile(temp_path));
        } catch (...) {
            std::filesystem::remove(temp_path);
            throw;
        }
        std::filesystem::remove(temp_path);

        const auto newline = result.find_first_of("\r\n");
        if (newline != std::string::npos) {
            result = Trim(result.substr(0, newline));
        }
        if (!result.empty()) {
            return result;
        }
    } catch (const std::exception& e) {
        LOG_WARNING("P3 follow-up generation failed, using fallback probe: {}", e.what());
    }

    const std::string fallback = kFallbacks[fallback_index % kFallbacks.size()];
    ++fallback_index;
    return fallback;
}

bool Part3Session::ShouldFollowUp(const std::string& answer) {
    const std::string text = Lowercase(answer);
    return WordCount(text) < 35 ||
           (text.find("because") == std::string::npos &&
            text.find("reason") == std::string::npos &&
            text.find("example") == std::string::npos);
}

} // namespace ielts
