#include "ielts/scorer.h"

#include "common/logger.h"
#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
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

float ClampBand(float value) {
    if (value < 0.0f) return 0.0f;
    if (value > 9.0f) return 9.0f;
    return std::round(value * 2.0f) / 2.0f;
}

float RoundedOverall(float fc, float lr, float gra, float p) {
    const float average = (fc + lr + gra + p) / 4.0f;
    return ClampBand(std::ceil(average * 2.0f) / 2.0f);
}

std::string ExtractJsonObject(const std::string& text) {
    const auto begin = text.find('{');
    const auto end = text.rfind('}');
    if (begin == std::string::npos || end == std::string::npos || end < begin) {
        throw std::runtime_error("Codex scorer output did not contain a JSON object");
    }
    return text.substr(begin, end - begin + 1);
}

IELTSScore HeuristicScore(const std::string& transcript, const std::string& reason) {
    const size_t words = std::count(transcript.begin(), transcript.end(), ' ') + (transcript.empty() ? 0 : 1);
    float base = 5.0f;
    if (words >= 180) base = 6.5f;
    else if (words >= 100) base = 6.0f;
    else if (words >= 50) base = 5.5f;
    else if (words < 20) base = 4.5f;

    IELTSScore score;
    score.fluency_coherence = ClampBand(base);
    score.lexical_resource = ClampBand(base);
    score.grammatical_range = ClampBand(base);
    score.pronunciation_estimate = ClampBand(base - 0.5f);
    score.overall_band = RoundedOverall(
        score.fluency_coherence,
        score.lexical_resource,
        score.grammatical_range,
        score.pronunciation_estimate
    );
    score.feedback = "Fallback estimate used because Codex scoring failed: " + reason;
    return score;
}

} // namespace

Scorer::Scorer(const std::string& data_dir) {
    system_prompt_ = ReadTextFile(std::filesystem::path(data_dir) / "prompts" / "scorer_system.md");
}

IELTSScore Scorer::Score(const std::string& transcript) {
    if (transcript.empty()) {
        return HeuristicScore(transcript, "empty transcript");
    }

    try {
        const std::string prompt = system_prompt_ + "\n\nTranscript:\n" + transcript + "\n";
        const std::string response = RunCodex(prompt);
        return ParseResponse(response);
    } catch (const std::exception& e) {
        LOG_ERROR("IELTS Codex scoring failed: {}", e.what());
        return HeuristicScore(transcript, e.what());
    }
}

std::string Scorer::RunCodex(const std::string& user_prompt) {
    const auto temp_path = std::filesystem::temp_directory_path() /
        ("ielts_scorer_" + std::to_string(::getpid()) + ".txt");

    {
        std::ofstream output(temp_path);
        if (!output) {
            throw std::runtime_error("Failed to write temporary Codex prompt: " + temp_path.string());
        }
        output << user_prompt;
    }

    const std::string codex = std::filesystem::exists("/opt/homebrew/bin/codex")
        ? "/opt/homebrew/bin/codex"
        : "codex";
    const std::string command =
        codex + " --model gpt-4o-mini --quiet --full-auto \"$(cat " +
        ShellQuote(temp_path.string()) + ")\" 2>/dev/null";

    std::array<char, 4096> buffer{};
    std::string result;
    FILE* pipe = ::popen(command.c_str(), "r");
    if (!pipe) {
        std::filesystem::remove(temp_path);
        throw std::runtime_error("Failed to start codex CLI");
    }

    while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe) != nullptr) {
        result += buffer.data();
    }
    const int status = ::pclose(pipe);
    std::filesystem::remove(temp_path);

    if (status == -1 || !WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        throw std::runtime_error("codex CLI exited with non-zero status");
    }
    if (result.empty()) {
        throw std::runtime_error("codex CLI returned empty output");
    }
    return result;
}

IELTSScore Scorer::ParseResponse(const std::string& json_response) {
    const auto parsed = nlohmann::json::parse(ExtractJsonObject(json_response));

    IELTSScore score;
    score.fluency_coherence = ClampBand(parsed.value("fluency_coherence", 0.0f));
    score.lexical_resource = ClampBand(parsed.value("lexical_resource", 0.0f));
    score.grammatical_range = ClampBand(parsed.value("grammatical_range", 0.0f));
    score.pronunciation_estimate = ClampBand(parsed.value("pronunciation_estimate", 0.0f));
    score.overall_band = RoundedOverall(
        score.fluency_coherence,
        score.lexical_resource,
        score.grammatical_range,
        score.pronunciation_estimate
    );
    score.feedback = parsed.value("feedback", "");
    return score;
}

} // namespace ielts
