#include "ielts/question_bank.h"

#include "common/logger.h"
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <random>
#include <stdexcept>
#include <nlohmann/json.hpp>

namespace ielts {

namespace {

bool IsJsonFile(const std::filesystem::directory_entry& entry) {
    return entry.is_regular_file() && entry.path().extension() == ".json";
}

nlohmann::json ReadJsonFile(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) {
        throw std::runtime_error("Failed to open IELTS question file: " + path.string());
    }

    nlohmann::json data;
    try {
        input >> data;
    } catch (const nlohmann::json::exception& e) {
        throw std::runtime_error("Failed to parse IELTS question file: " + path.string() + " " + e.what());
    }
    return data;
}

} // namespace

void QuestionBank::LoadPart1(const std::string& data_dir) {
    p1_questions_.clear();

    const std::filesystem::path part1_dir = std::filesystem::path(data_dir) / "part1";
    if (!std::filesystem::exists(part1_dir)) {
        throw std::runtime_error("IELTS Part 1 directory does not exist: " + part1_dir.string());
    }

    for (const auto& entry : std::filesystem::directory_iterator(part1_dir)) {
        if (!IsJsonFile(entry)) {
            continue;
        }

        const auto data = ReadJsonFile(entry.path());
        if (data.value("part", 0) != 1) {
            LOG_WARNING("Skipping non-Part-1 IELTS file: {}", entry.path().string());
            continue;
        }

        const std::string topic = data.value("topic", entry.path().stem().string());
        const auto questions = data.value("questions", nlohmann::json::array());
        if (!questions.is_array()) {
            throw std::runtime_error("Part 1 questions must be an array: " + entry.path().string());
        }

        for (const auto& q : questions) {
            if (q.is_string() && !q.get<std::string>().empty()) {
                p1_questions_.push_back(P1Question{topic, q.get<std::string>()});
            }
        }
    }

    if (p1_questions_.empty()) {
        throw std::runtime_error("No IELTS Part 1 questions loaded from: " + part1_dir.string());
    }

    LOG_INFO("Loaded {} IELTS Part 1 questions", p1_questions_.size());
}

void QuestionBank::LoadPart2(const std::string& data_dir) {
    p2_topics_.clear();

    const std::filesystem::path part2_dir = std::filesystem::path(data_dir) / "part2";
    if (!std::filesystem::exists(part2_dir)) {
        throw std::runtime_error("IELTS Part 2 directory does not exist: " + part2_dir.string());
    }

    for (const auto& entry : std::filesystem::directory_iterator(part2_dir)) {
        if (!IsJsonFile(entry)) {
            continue;
        }

        const auto data = ReadJsonFile(entry.path());
        if (data.value("part", 0) != 2) {
            LOG_WARNING("Skipping non-Part-2 IELTS file: {}", entry.path().string());
            continue;
        }

        const auto topics = data.value("topics", nlohmann::json::array());
        if (!topics.is_array()) {
            throw std::runtime_error("Part 2 topics must be an array: " + entry.path().string());
        }

        for (const auto& item : topics) {
            P2Topic topic;
            topic.title = item.value("title", "");
            topic.rounding = item.value("rounding", "");
            topic.p3_theme = item.value("p3_theme", topic.title);

            const auto bullets = item.value("bullets", nlohmann::json::array());
            if (bullets.is_array()) {
                for (const auto& bullet : bullets) {
                    if (bullet.is_string()) {
                        topic.bullets.push_back(bullet.get<std::string>());
                    }
                }
            }

            if (!topic.title.empty() && !topic.bullets.empty()) {
                p2_topics_.push_back(std::move(topic));
            }
        }
    }

    if (p2_topics_.empty()) {
        throw std::runtime_error("No IELTS Part 2 topics loaded from: " + part2_dir.string());
    }

    LOG_INFO("Loaded {} IELTS Part 2 topics", p2_topics_.size());
}

std::vector<P1Question> QuestionBank::SampleP1Questions(int n) const {
    if (p1_questions_.empty()) {
        throw std::runtime_error("IELTS Part 1 question bank is empty");
    }

    std::vector<P1Question> questions = p1_questions_;
    static thread_local std::mt19937 rng(std::random_device{}());
    std::shuffle(questions.begin(), questions.end(), rng);

    const int count = std::max(1, std::min(n, static_cast<int>(questions.size())));
    questions.resize(static_cast<size_t>(count));
    return questions;
}

P2Topic QuestionBank::SampleP2Topic() const {
    if (p2_topics_.empty()) {
        throw std::runtime_error("IELTS Part 2 topic bank is empty");
    }

    static thread_local std::mt19937 rng(std::random_device{}());
    std::uniform_int_distribution<size_t> dist(0, p2_topics_.size() - 1);
    return p2_topics_[dist(rng)];
}

int QuestionBank::Part1Count() const {
    return static_cast<int>(p1_questions_.size());
}

int QuestionBank::Part2Count() const {
    return static_cast<int>(p2_topics_.size());
}

} // namespace ielts
