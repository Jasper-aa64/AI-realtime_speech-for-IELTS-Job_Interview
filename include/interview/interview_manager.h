/**
 * @file interview_manager.h
 * @brief 面试会话管理模块
 *
 * 负责管理技术面试的完整生命周期：问题生成、回答记录、LLM评分与报告导出。
 * 支持简历驱动（针对性提问）和默认 C++ 题库两种工作模式。
 */

#pragma once

#include <memory>
#include <string>
#include <nlohmann/json.hpp>

namespace interview {
namespace session {

/**
 * @brief 面试会话
 *
 * 封装单次技术面试的全部状态与逻辑，对外提供线性的面试驱动接口。
 *
 * 工作模式：
 * - 简历驱动：解析 PDF 简历，由 LLM 生成针对候选人背景的问题（推荐）
 * - 默认题库：生成通用 C++ 技术面试题
 *
 * 典型使用流程：
 * @code
 * auto session = std::make_shared<InterviewSession>("张三");
 * session->LoadQuestionsFromResume("resume.pdf", 20);
 * session->EnableLLMScoring(true);
 *
 * std::string q = session->GetFirstQuestion();
 * session->RecordAnswer("...");
 * if (session->ShouldFollowUp()) q = session->GetFollowUpQuestion();
 * else q = session->GetNextQuestion();
 *
 * session->SaveReport();
 * @endcode
 *
 * @note 非线程安全，应在单线程（DialogSession 主线程）中使用。
 */
class InterviewSession {
public:
    /**
     * @param candidate_name 候选人姓名，用于报告和开场白个性化
     */
    explicit InterviewSession(const std::string& candidate_name = "候选人");
    ~InterviewSession();

    /**
     * @brief 生成默认 C++ 面试题
     *
     * 无简历时使用，由 LLM 生成覆盖基础语法、内存管理、STL、OOP、
     * C++11/14/17、多线程、设计模式等方向的通用题目。
     *
     * @param num_questions 期望生成的题目数量，默认 15
     * @throws std::runtime_error LLM 调用失败
     */
    void GenerateDefaultQuestions(int num_questions = 15);

    /**
     * @brief 从 PDF 简历生成针对性问题
     *
     * 解析简历后调用 LLM，根据候选人项目经验和技术栈生成问题。
     *
     * @param resume_pdf_path PDF 简历的绝对路径（不支持扫描件）
     * @param min_questions   最少生成的题目数量，默认 15
     * @throws std::runtime_error PDF 解析或 LLM 生成失败
     */
    void LoadQuestionsFromResume(const std::string& resume_pdf_path, int min_questions = 15);

    /**
     * @brief 返回开场白提示词（驱动 AI 问候并引导自我介绍）
     */
    std::string GetIntroPrompt() const;

    /**
     * @brief 返回第一个技术问题提示词，进入 WARM_UP 阶段
     * @throws std::runtime_error 问题未加载
     */
    std::string GetFirstQuestion();

    /**
     * @brief 返回下一个问题提示词，并自动推进面试阶段
     * @return 下一个问题提示词；所有问题问完后返回空字符串
     */
    std::string GetNextQuestion();

    /**
     * @brief 返回 LLM 生成的追问提示词
     *
     * 调用后自动清除追问状态，防止对同一题重复追问。
     *
     * @return 追问提示词；无需追问时返回空字符串
     */
    std::string GetFollowUpQuestion();

    /**
     * @brief 记录候选人回答并触发 LLM 评分
     *
     * 评分结果含分数、反馈及是否追问标志，可通过 GetLastScore() /
     * ShouldFollowUp() 查询。
     *
     * @param answer ASR 识别的回答文本
     */
    void RecordAnswer(const std::string& answer);

    /** @return 上一次回答的得分（0-100），无记录时返回 0 */
    int GetLastScore() const;

    /** @return true 表示需要对上一次回答追问 */
    bool ShouldFollowUp() const;

    /** @return true 表示所有题目均已提问完毕 */
    bool IsComplete() const;

    /**
     * @brief 使用 LLM 生成面试总结
     * @return 中文自然语言总结（含技术评价、薄弱点、录用建议）
     */
    std::string GenerateSummary() const;

    /**
     * @brief 生成结构化面试报告
     *
     * 报告字段：candidate_name、interview_date、duration_minutes、
     * total_questions、average_score、total_score、records、evaluation。
     *
     * @return nlohmann::json 对象
     */
    nlohmann::json GenerateReport() const;

    /**
     * @brief 将报告写入 JSON 文件
     * @param filename 文件名，默认自动生成（interview_report_YYYYMMDD_HHMMSS.json）
     * @return 实际写入的文件路径
     * @throws std::runtime_error 文件写入失败
     */
    std::string SaveReport(const std::string& filename = "") const;

    int GetCurrentQuestionIndex() const;

private:
    class InterviewSessionImpl;
    std::unique_ptr<InterviewSessionImpl> pimpl_;
};

} // namespace session
} // namespace interview
