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

std::string CodexBinary() {
    return std::filesystem::exists("/opt/homebrew/bin/codex")
        ? "/opt/homebrew/bin/codex"
        : "codex";
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

Scorer::Scorer(const std::string& data_dir, ScorerConfig config)
    : config_(std::move(config)) {
    system_prompt_ = ReadTextFile(std::filesystem::path(data_dir) / "prompts" / "scorer_system.md");
}

IELTSScore Scorer::Score(const std::string& transcript) {
    if (transcript.empty()) {
        return HeuristicScore(transcript, "empty transcript");
    }

    try {
        const std::string backend_name =
            config_.backend == ScorerBackend::kCodexExec  ? "codex_exec" :
            config_.backend == ScorerBackend::kOpenAIAPI  ? "openai_api" :
            config_.backend == ScorerBackend::kClaude     ? "claude"     : "heuristic";
        LOG_INFO("IELTS Scorer backend: {}", backend_name);

        const std::string prompt = system_prompt_ + "\n\nTranscript:\n" + transcript + "\n";
        const std::string response = RunBackend(prompt);
        return ParseResponse(response);
    } catch (const std::exception& e) {
        LOG_ERROR("IELTS scoring failed: {}", e.what());
        return HeuristicScore(transcript, e.what());
    }
}

std::string Scorer::RunBackend(const std::string& prompt) {
    switch (config_.backend) {
        case ScorerBackend::kCodexExec:  return RunCodexExec(prompt);
        case ScorerBackend::kOpenAIAPI:  return RunOpenAIAPI(prompt);
        case ScorerBackend::kClaude:     return RunClaude(prompt);
        case ScorerBackend::kHeuristic:  throw std::runtime_error("heuristic backend selected");
    }
    throw std::runtime_error("unknown backend");
}

std::string Scorer::RunCodexExec(const std::string& prompt) {
    const auto temp_path = std::filesystem::temp_directory_path() /
        ("ielts_scorer_" + std::to_string(::getpid()) + ".txt");
    {
        std::ofstream out(temp_path);
        if (!out) throw std::runtime_error("Failed to write prompt file");
        out << prompt;
    }

    const std::string codex_bin = std::filesystem::exists("/opt/homebrew/bin/codex")
        ? "/opt/homebrew/bin/codex" : "codex";

    std::string cmd = "cat " + ShellQuote(temp_path.string()) + " | " + ShellQuote(codex_bin) + " exec";
    if (!config_.model.empty()) {
        cmd += " -m " + ShellQuote(config_.model);
    }
    cmd += " 2>/dev/null";

    std::array<char, 8192> buf{};
    std::string result;
    FILE* pipe = ::popen(cmd.c_str(), "r");
    std::filesystem::remove(temp_path);
    if (!pipe) throw std::runtime_error("Failed to start codex CLI");
    while (fgets(buf.data(), static_cast<int>(buf.size()), pipe)) result += buf.data();
    const int status = ::pclose(pipe);
    if (status == -1 || !WIFEXITED(status) || WEXITSTATUS(status) != 0)
        throw std::runtime_error("codex exec exited with non-zero status");
    if (result.empty()) throw std::runtime_error("codex exec returned empty output");
    return result;
}

std::string Scorer::RunOpenAIAPI(const std::string& prompt) {
    const auto temp_path = std::filesystem::temp_directory_path() /
        ("ielts_scorer_api_" + std::to_string(::getpid()) + ".txt");
    {
        std::ofstream out(temp_path);
        if (!out) throw std::runtime_error("Failed to write prompt file");
        out << prompt;
    }

    const std::string codex_bin = std::filesystem::exists("/opt/homebrew/bin/codex")
        ? "/opt/homebrew/bin/codex" : "codex";
    const std::string model = config_.model.empty() ? "gpt-4o" : config_.model;

    if (!config_.api_key.empty()) {
        ::setenv("OPENAI_API_KEY", config_.api_key.c_str(), 1);
    }

    std::string cmd = "cat " + ShellQuote(temp_path.string()) + " | " +
        ShellQuote(codex_bin) + " exec -m " + ShellQuote(model) + " 2>/dev/null";

    std::array<char, 8192> buf{};
    std::string result;
    FILE* pipe = ::popen(cmd.c_str(), "r");
    std::filesystem::remove(temp_path);
    if (!pipe) throw std::runtime_error("Failed to start codex CLI (openai_api)");
    while (fgets(buf.data(), static_cast<int>(buf.size()), pipe)) result += buf.data();
    const int status = ::pclose(pipe);
    if (status == -1 || !WIFEXITED(status) || WEXITSTATUS(status) != 0)
        throw std::runtime_error("codex exec (openai_api) exited with non-zero status");
    if (result.empty()) throw std::runtime_error("codex exec (openai_api) returned empty output");
    return result;
}

std::string Scorer::RunClaude(const std::string& prompt) {
    const std::string home = std::getenv("HOME") ? std::getenv("HOME") : "";
    const std::string claude_bin = std::filesystem::exists(home + "/.local/bin/claude")
        ? home + "/.local/bin/claude" : "claude";

    const auto temp_path = std::filesystem::temp_directory_path() /
        ("ielts_scorer_claude_" + std::to_string(::getpid()) + ".txt");
    {
        std::ofstream out(temp_path);
        if (!out) throw std::runtime_error("Failed to write claude prompt");
        out << prompt;
    }

    std::string cmd = "cat " + ShellQuote(temp_path.string()) + " | " +
        ShellQuote(claude_bin) + " --print 2>/dev/null";

    std::array<char, 8192> buf{};
    std::string result;
    FILE* pipe = ::popen(cmd.c_str(), "r");
    std::filesystem::remove(temp_path);
    if (!pipe) throw std::runtime_error("Failed to start claude CLI");
    while (fgets(buf.data(), static_cast<int>(buf.size()), pipe)) result += buf.data();
    const int status = ::pclose(pipe);
    if (status == -1 || !WIFEXITED(status) || WEXITSTATUS(status) != 0)
        throw std::runtime_error("claude CLI exited with non-zero status");
    if (result.empty()) throw std::runtime_error("claude CLI returned empty output");
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
