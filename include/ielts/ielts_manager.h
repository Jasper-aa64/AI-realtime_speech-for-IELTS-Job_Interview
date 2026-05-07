#pragma once
#include "ielts/question_bank.h"
#include "ielts/scorer.h"
#include <string>
#include <nlohmann/json.hpp>

namespace interview { namespace services { class RealtimeClient; } }

namespace ielts {

enum class ExamMode {
    kFullExam,   // P1 + P2 + P3
    kPart1Only,
    kPart2Only,
    kPart3Only,  // requires a P2Topic to be specified
};

class IELTSManager {
public:
    // data_dir: path to data/ielts/
    // report_dir: where to write reports/ (default: project root reports/)
    IELTSManager(const std::string& data_dir,
                 const std::string& report_dir,
                 interview::services::RealtimeClient& rt_client);

    void RunExam(ExamMode mode = ExamMode::kFullExam);

    // Returns path to the saved report
    std::string GetLastReportPath() const;

private:
    void GenerateReport(const nlohmann::json& p1_data,
                        const nlohmann::json& p2_data,
                        const nlohmann::json& p3_data);

    static void PrintScoreSummary(const IELTSScore& s, const std::string& part_name);

    std::string                            data_dir_;
    std::string                            report_dir_;
    interview::services::RealtimeClient&   rt_client_;
    QuestionBank                           bank_;
    Scorer                                 scorer_;
    std::string                            last_report_path_;
};

} // namespace ielts
