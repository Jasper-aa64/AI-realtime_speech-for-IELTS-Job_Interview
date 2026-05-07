#include "ielts/part3_session.h"

#include "common/logger.h"
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
        std::cout << "Candidate answer transcript:\n> ";
        std::string answer;
        std::getline(std::cin, answer);
        transcript_ += "Examiner: " + question + "\nCandidate: " + answer + "\n";

        if (ShouldFollowUp(answer)) {
            const std::string follow_up = "Why do you think that is the case?";
            std::cout << "\033[1;33mFollow-up:\033[0m " << follow_up << "\n";
            SafeSpeak(rt_client_, follow_up);
            std::cout << "Candidate follow-up answer transcript:\n> ";
            std::string follow_answer;
            std::getline(std::cin, follow_answer);
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

        const std::string claude = std::filesystem::exists(std::filesystem::path(std::getenv("HOME") ? std::getenv("HOME") : "") / ".local/bin/claude")
            ? (std::filesystem::path(std::getenv("HOME")) / ".local/bin/claude").string()
            : "claude";
        const std::string command = claude + " -p \"$(cat " + ShellQuote(temp_path.string()) + ")\" --allowedTools none -- " +
            ShellQuote("P2 Topic: " + p2_topic_.title + ", Theme: " + theme) + " 2>/dev/null";

        std::array<char, 4096> buffer{};
        std::string result;
        FILE* pipe = ::popen(command.c_str(), "r");
        if (!pipe) {
            std::filesystem::remove(temp_path);
            throw std::runtime_error("Failed to start claude CLI");
        }
        while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe) != nullptr) {
            result += buffer.data();
        }
        const int status = ::pclose(pipe);
        std::filesystem::remove(temp_path);
        if (status == -1 || !WIFEXITED(status) || WEXITSTATUS(status) != 0 || result.empty()) {
            throw std::runtime_error("claude CLI did not return questions");
        }

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

bool Part3Session::ShouldFollowUp(const std::string& answer) {
    const std::string text = Lowercase(answer);
    return WordCount(text) < 35 ||
           (text.find("because") == std::string::npos &&
            text.find("reason") == std::string::npos &&
            text.find("example") == std::string::npos);
}

} // namespace ielts
