#pragma once
#include <string>

namespace ielts {

enum class ScorerBackend { kCodexExec, kOpenAIAPI, kClaude, kHeuristic };

struct ScorerConfig {
    ScorerBackend backend = ScorerBackend::kCodexExec;
    std::string   model;    // empty = use backend default
    std::string   api_key;  // for kOpenAIAPI mode
};

struct IELTSScore {
    float fluency_coherence    = 0.0f;
    float lexical_resource     = 0.0f;
    float grammatical_range    = 0.0f;
    float pronunciation_estimate = 0.0f;
    float overall_band         = 0.0f;
    std::string feedback;
};

class Scorer {
public:
    // data_dir: path to data/ielts/ — loads prompts/scorer_system.md
    explicit Scorer(const std::string& data_dir, ScorerConfig config = {});

    // Score an English speaking transcript; calls configured backend via popen()
    IELTSScore Score(const std::string& transcript);

private:
    std::string system_prompt_;
    ScorerConfig config_;
    std::string RunBackend(const std::string& prompt);
    std::string RunCodexExec(const std::string& prompt);
    std::string RunOpenAIAPI(const std::string& prompt);
    std::string RunClaude(const std::string& prompt);
    IELTSScore  ParseResponse(const std::string& json_response);
};

} // namespace ielts
