#include "ielts/ielts_manager.h"

#include "ielts/part1_session.h"
#include "ielts/part2_session.h"
#include "ielts/part3_session.h"
#include "common/logger.h"
#include <ctime>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>

namespace ielts {

namespace {

nlohmann::json ScoreToJson(const IELTSScore& score) {
    return {
        {"fluency_coherence", score.fluency_coherence},
        {"lexical_resource", score.lexical_resource},
        {"grammatical_range", score.grammatical_range},
        {"pronunciation_estimate", score.pronunciation_estimate},
        {"overall_band", score.overall_band},
        {"feedback", score.feedback}
    };
}

std::string NowIso8601() {
    auto now = std::time(nullptr);
    std::tm tm{};
    localtime_r(&now, &tm);
    std::ostringstream oss;
    oss << std::put_time(&tm, "%Y-%m-%dT%H:%M:%S");
    return oss.str();
}

std::string NowFilename() {
    auto now = std::time(nullptr);
    std::tm tm{};
    localtime_r(&now, &tm);
    std::ostringstream oss;
    oss << std::put_time(&tm, "%Y%m%d_%H%M%S");
    return oss.str();
}

float AverageOverall(const nlohmann::json& p1, const nlohmann::json& p2, const nlohmann::json& p3) {
    float total = 0.0f;
    int count = 0;
    for (const auto* part : {&p1, &p2, &p3}) {
        if (part->contains("score")) {
            total += (*part)["score"].value("overall_band", 0.0f);
            ++count;
        }
    }
    if (count == 0) {
        return 0.0f;
    }
    return std::ceil((total / static_cast<float>(count)) * 2.0f) / 2.0f;
}

} // namespace

IELTSManager::IELTSManager(const std::string& data_dir,
                           const std::string& report_dir,
                           interview::services::RealtimeClient& rt_client)
    : data_dir_(data_dir)
    , report_dir_(report_dir)
    , rt_client_(rt_client)
    , scorer_(data_dir) {
    bank_.LoadPart1(data_dir_);
    bank_.LoadPart2(data_dir_);
}

void IELTSManager::RunExam(ExamMode mode) {
    nlohmann::json p1_data;
    nlohmann::json p2_data;
    nlohmann::json p3_data;
    P2Topic p2_topic;

    if (mode == ExamMode::kFullExam || mode == ExamMode::kPart1Only) {
        Part1Session p1(bank_, rt_client_, scorer_, 5);
        p1.Start();
        PrintScoreSummary(p1.GetScore(), "Part 1");
        p1_data = {
            {"score", ScoreToJson(p1.GetScore())},
            {"transcript", p1.GetTranscript()}
        };
    }

    if (mode == ExamMode::kFullExam || mode == ExamMode::kPart2Only || mode == ExamMode::kPart3Only) {
        if (mode == ExamMode::kPart3Only) {
            p2_topic = bank_.SampleP2Topic();
        } else {
            Part2Session p2(bank_, rt_client_, scorer_, report_dir_);
            p2.Start();
            p2_topic = p2.GetTopic();
            PrintScoreSummary(p2.GetScore(), "Part 2");
            p2_data = {
                {"topic", p2_topic.title},
                {"theme", p2_topic.p3_theme},
                {"duration_seconds", p2.GetActualDuration()},
                {"score", ScoreToJson(p2.GetScore())},
                {"transcript", p2.GetTranscript()}
            };
        }
    }

    if (mode == ExamMode::kFullExam || mode == ExamMode::kPart3Only) {
        Part3Session p3(p2_topic, rt_client_, scorer_, data_dir_);
        p3.Start();
        PrintScoreSummary(p3.GetScore(), "Part 3");
        p3_data = {
            {"theme", p2_topic.p3_theme},
            {"score", ScoreToJson(p3.GetScore())},
            {"transcript", p3.GetTranscript()}
        };
    }

    GenerateReport(p1_data, p2_data, p3_data);
}

std::string IELTSManager::GetLastReportPath() const {
    return last_report_path_;
}

void IELTSManager::GenerateReport(const nlohmann::json& p1_data,
                                  const nlohmann::json& p2_data,
                                  const nlohmann::json& p3_data) {
    std::filesystem::create_directories(report_dir_);
    const auto path = std::filesystem::path(report_dir_) / ("ielts_" + NowFilename() + ".json");

    nlohmann::json report;
    report["timestamp"] = NowIso8601();
    report["candidate"] = "User";
    report["parts"] = nlohmann::json::object();
    if (!p1_data.empty()) report["parts"]["part1"] = p1_data;
    if (!p2_data.empty()) report["parts"]["part2"] = p2_data;
    if (!p3_data.empty()) report["parts"]["part3"] = p3_data;

    report["overall"]["band"] = AverageOverall(p1_data, p2_data, p3_data);
    report["overall"]["feedback"] = "Review the per-part feedback and repeat weak parts with longer, better-supported answers.";

    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("Failed to write IELTS report: " + path.string());
    }
    output << report.dump(2);
    last_report_path_ = path.string();

    LOG_INFO("IELTS report saved: {}", last_report_path_);
    std::cout << "\nReport saved: " << last_report_path_ << "\n";
}

void IELTSManager::PrintScoreSummary(const IELTSScore& s, const std::string& part_name) {
    std::cout << "\n\033[1;32m" << part_name << " score\033[0m\n"
              << "  Fluency & Coherence: " << s.fluency_coherence << "\n"
              << "  Lexical Resource: " << s.lexical_resource << "\n"
              << "  Grammar: " << s.grammatical_range << "\n"
              << "  Pronunciation estimate: " << s.pronunciation_estimate << "\n"
              << "  Overall band: " << s.overall_band << "\n"
              << "  Feedback: " << s.feedback << "\n";
}

} // namespace ielts
