#pragma once
#include <string>

namespace ielts {

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
    explicit Scorer(const std::string& data_dir);

    // Score an English speaking transcript; calls codex CLI via popen()
    IELTSScore Score(const std::string& transcript);

private:
    std::string system_prompt_;
    std::string RunCodex(const std::string& user_prompt);
    IELTSScore  ParseResponse(const std::string& json_response);
};

} // namespace ielts
