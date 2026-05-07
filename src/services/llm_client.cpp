#include "services/llm_client.h"
#include <curl/curl.h>
#include "common/logger.h"
#include "common/utils.h"
#include "common/config.h"

namespace interview {
namespace services {

class LLMClient::LLMClientImpl {
public:
    static size_t WriteCallback(void* contents, size_t size, size_t nmemb, void* userp) {
        size_t total_size = size * nmemb;
        std::string* response = static_cast<std::string*>(userp);
        response->append(static_cast<char*>(contents), total_size);
        return total_size;
    }
    
    LLMClientImpl() {
        // 初始化用于调用 LLM API 的 HTTP/网络资源。
        curl_global_init(CURL_GLOBAL_DEFAULT);
    }

    ~LLMClientImpl() {
        // 清理 HTTP/网络资源。
        curl_global_cleanup(); 
    }

    std::string CallAPI(const nlohmann::json& request_body) {
        // 将 request_body 发送到配置的 LLM 接口，并返回原始响应字符串。
        auto cfg = common::Config::Instance().llm_config;
        if (cfg.api_key.empty()) {
            throw std::runtime_error("LLM API key not configured");
        }
        if (cfg.api_url.empty()) {
            throw std::runtime_error("LLM API URL not configured");
        }
        CURL* curl = curl_easy_init();
        if (!curl) {
            throw std::runtime_error("Failed to initialize curl");
        }
        
        std::string request_json = request_body.dump();
        LOG_INFO("=== LLM API Request ===");
        LOG_INFO("URL: {}", cfg.api_url);
        LOG_INFO("Model: {}", cfg.model);
        LOG_INFO("Request Body:\n{}", request_body.dump(2));

        std::string response_string;
        struct curl_slist* headers = nullptr;

        try {
            headers = curl_slist_append(headers, "Content-Type: application/json; charset=utf-8");
            std::string auth_header = "Authorization: Bearer " + cfg.api_key;
            headers = curl_slist_append(headers, auth_header.c_str());

            // 设置CURL选项
            curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
            curl_easy_setopt(curl, CURLOPT_URL, cfg.api_url.c_str());
            curl_easy_setopt(curl, CURLOPT_POSTFIELDS, request_json.c_str());
            curl_easy_setopt(curl, CURLOPT_TIMEOUT, cfg.timeout_seconds);
            curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
            curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_string);

            // 执行请求
            CURLcode res = curl_easy_perform(curl);

            if (res != CURLE_OK) {
                std::string error = "CURL request failed: " + std::string(curl_easy_strerror(res));
                throw std::runtime_error(error);
            }
            // 检查响应状态码
            long http_code = 0;
            curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
            
            LOG_INFO("=== LLM API Response ===");
            LOG_INFO("HTTP Status: {}", http_code);
            LOG_INFO("Response Body:\n{}", response_string);

            if (http_code != 200) {
                LOG_ERROR("LLM API returned error: {}", response_string);
                throw std::runtime_error("LLM API returned error: " + response_string);
            }

            curl_easy_cleanup(curl);
            curl_slist_free_all(headers);

            return response_string;
        } catch (const std::exception& e) {
            curl_easy_cleanup(curl);
            curl_slist_free_all(headers);
            LOG_ERROR("Error in LLM API call: {}", e.what());
            throw;
        } 
    }

    // 基于对话消息构建与服务端兼容的请求 JSON。
    nlohmann::json BuildRequestBody(const std::vector<Message>& messages) {
        auto& cfg = common::Config::Instance().llm_config;
        
        nlohmann::json request;

        // 构建 LLM API 请求体，兼容 server 预期结构
        nlohmann::json model_config;
        model_config["name"] = cfg.model;  // 模型名称放在 model_config.name
        model_config["temperature"] = cfg.temperature;
        model_config["max_tokens"] = cfg.max_tokens;
        request["model_config"] = model_config;

        // 同时保留顶层的model字段以兼容其他API
        request["model"] = cfg.model;
        request["temperature"] = cfg.temperature;
        request["max_tokens"] = cfg.max_tokens;

        // 封装消息
        nlohmann::json arr = nlohmann::json::array();
        for(const auto& msg : messages){
            nlohmann::json item;
            item["role"] = msg.role;
            item["content"] = msg.content;
            arr.push_back(item);
        }
        request["messages"] = arr;

        return request;
    }

    std::string ExtractResponse(const std::string& response_str) {
        try {
            // 解析 LLM API JSON 响应，提取 assistant 生成的文本内容
            auto response_json = nlohmann::json::parse(response_str);

            // 检查返回格式，确认包含 choices 列表且非空
            if (response_json.contains("choices") && !response_json["choices"].empty()) {
                const auto& choice = response_json["choices"][0];
                // message.content 是常见的返回格式
                if (choice.contains("message") && choice["message"].contains("content")) {
                    return choice["message"]["content"].get<std::string>();
                }
                // 兼容 legacy 格式，直接有 text 字段
                if (choice.contains("text")) {
                    return choice["text"].get<std::string>();
                }
            }
            throw std::runtime_error("Invalid response format from LLM API: missing expected keys.");
        } catch (const nlohmann::json::exception& e) {
            throw std::runtime_error("Failed to parse LLM response: " + std::string(e.what()));
        }
    }
};

LLMClient::LLMClient()
    : pimpl_(std::make_unique<LLMClientImpl>()) {
}

LLMClient::~LLMClient() = default;

std::string LLMClient::SendMessage(const std::string& message, const std::string& system_prompt) {
    std::vector<Message> messages;

    if (!system_prompt.empty()) {
        messages.push_back({"system", system_prompt});
    }
    messages.push_back({"user", message});

    return SendConversation(messages);
}

std::string LLMClient::SendConversation(const std::vector<Message>& messages) {
    auto request_body = pimpl_->BuildRequestBody(messages);

    LOG_INFO("Sending request to LLM API...");
    std::string response_str = pimpl_->CallAPI(request_body);

    std::string content = pimpl_->ExtractResponse(response_str);

    LOG_INFO("=== LLM Extracted Content ===");
    LOG_INFO("Content:\n{}", content);

    return content;
}

nlohmann::json LLMClient::GenerateQuestionsFromResume(const std::string& resume_text, int min_questions) {
    std::string system_prompt = 
        u8"你是一位资深的C++技术面试官。请仔细阅读候选人的简历，并根据简历内容生成至少" +
        std::to_string(min_questions) + 
        u8"个技术面试问题。\n\n"
        "要求：\n"
        "1. 问题必须与候选人简历中的项目经验、技术栈紧密相关\n"
        "2. 难度分布：30%基础题、50%中级题、20%高级题\n"
        "3. 覆盖C++核心知识：语法、内存管理、面向对象、STL、多线程、性能优化等\n"
        "4. 每个问题都要有明确的考察点\n"
        "5. 问题要具体、可量化评估\n\n"
        "请以JSON数组格式返回问题列表，每个问题包含以下字段：\n"
        "- question: 问题内容\n"
        "- category: 类别（如\"内存管理\"、\"多线程\"等）\n"
        "- level: 难度（basic/intermediate/advanced）\n"
        "- key_points: 关键考察点数组\n"
        "- expected_keywords: 期望答案中包含的关键词数组\n\n"
        "示例格式：\n"
        "[\n"
        "  {\n"
        "    \"question\": \"在你的XX项目中，如何管理内存以避免内存泄漏？\",\n"
        "    \"category\": \"内存管理\",\n"
        "    \"level\": \"intermediate\",\n"
        "    \"key_points\": [\"智能指针\", \"RAII\", \"资源管理\"],\n"
        "    \"expected_keywords\": [\"shared_ptr\", \"unique_ptr\", \"RAII\", \"析构函数\"]\n"
        "  }\n"
        "]";

    std::string user_prompt = "候选人简历内容：\n\n" + resume_text +
    "\n\n请根据以上简历生成" + std::to_string(min_questions) +
    "个面试问题，以JSON格式返回。";

    LOG_INFO(">>> Calling LLM: GenerateQuestionsFromResume");
    LOG_INFO("Resume text length: {} characters", resume_text.length());
    LOG_INFO("Requested questions: {}", min_questions);

    std::string response = SendMessage(user_prompt, system_prompt);

    try {
        // 使用utils中的JSON解析函数
        auto questions = common::ParseJSONFromResponse(response, '[', ']');

        if (questions.empty() || !questions.is_array()) {
            LOG_ERROR("Parsed JSON is not a valid array or is empty");
            throw std::runtime_error("Invalid questions array format");
        }

        LOG_INFO("Generated {} questions from resume", questions.size());
        return questions;

    } catch (const nlohmann::json::exception& e) {
        LOG_ERROR("JSON parse error: {}", e.what());
        LOG_ERROR("Response that failed to parse: {}", response);
        throw std::runtime_error("Failed to parse questions JSON: " + std::string(e.what()));
    } catch (const std::exception& e) {
        LOG_ERROR("Failed to parse questions JSON: {}", e.what());
        throw std::runtime_error("Failed to generate questions from resume: " + std::string(e.what()));
    }
}

nlohmann::json LLMClient::GenerateQuestionsFromRequirements(const std::string& job_requirements, int min_questions) {
    std::string system_prompt =
        u8"你是一位资深的C++技术面试官。请根据岗位要求生成至少" +
        std::to_string(min_questions) +
        u8"个技术面试问题。\n\n"
        "要求：\n"
        "1. 问题必须围绕岗位要求中的核心能力，优先考察工程实践能力\n"
        "2. 难度分布：30%基础题、50%中级题、20%高级题\n"
        "3. 覆盖C++核心知识：语法、内存管理、面向对象、STL、多线程、性能优化等\n"
        "4. 每个问题都要有明确的考察点\n"
        "5. 问题要具体、可量化评估\n\n"
        "请以JSON数组格式返回问题列表，每个问题包含以下字段：\n"
        "- question: 问题内容\n"
        "- category: 类别（如\"内存管理\"、\"多线程\"等）\n"
        "- level: 难度（basic/intermediate/advanced）\n"
        "- key_points: 关键考察点数组\n"
        "- expected_keywords: 期望答案中包含的关键词数组\n";

    std::string user_prompt = "岗位要求：\n\n" + job_requirements +
        "\n\n请根据以上岗位要求生成" + std::to_string(min_questions) +
        "个面试问题，以JSON格式返回。";

    LOG_INFO(">>> Calling LLM: GenerateQuestionsFromRequirements");
    LOG_INFO("Requirements text length: {} characters", job_requirements.length());
    LOG_INFO("Requested questions: {}", min_questions);

    std::string response = SendMessage(user_prompt, system_prompt);

    try {
        auto questions = common::ParseJSONFromResponse(response, '[', ']');

        if (questions.empty() || !questions.is_array()) {
            LOG_ERROR("Parsed JSON is not a valid array or is empty");
            throw std::runtime_error("Invalid questions array format");
        }

        LOG_INFO("Generated {} questions from requirements", questions.size());
        return questions;

    } catch (const nlohmann::json::exception& e) {
        LOG_ERROR("JSON parse error: {}", e.what());
        LOG_ERROR("Response that failed to parse: {}", response);
        throw std::runtime_error("Failed to parse questions JSON: " + std::string(e.what()));
    } catch (const std::exception& e) {
        LOG_ERROR("Failed to parse questions JSON: {}", e.what());
        throw std::runtime_error("Failed to generate questions from requirements: " + std::string(e.what()));
    }
}

nlohmann::json LLMClient::EvaluateAnswer(const std::string& question, const std::string& answer) {
    std::string system_prompt = R"(你是一位资深的C++技术面试官，以严格、客观的标准评估候选人的回答。

    评分标准（0-100分）- 请严格执行：
    - 90-100分：回答准确、深入、全面，展现了深厚的技术功底和实战经验
    - 70-89分：回答正确且清晰，涵盖主要知识点，但细节深度不够
    - 50-69分：基本理解核心概念，但有明显遗漏、不够准确或深度不足
    - 30-49分：理解片面，答案不完整，存在明显错误
    - 0-29分：答非所问、完全错误或根本不理解

    追问判断标准（追问应有针对性，避免过度追问）：
    - 分数60-80分：回答有一定理解但深度不够，可通过1次追问考察细节
    - 分数<60分：理解不足，无需追问，直接进入下一题
    - 分数>80分：回答优秀，无需追问
    - 特别注意：如果候选人回答明显不靠谱、胡说八道或敷衍，请给予低分（<50）且不追问

    评分原则：
    1. 对于错误或不相关的回答，请大胆给予低分
    2. 不要因为回答了"一点东西"就给及格分
    3. 评估要看答案的准确性、完整性和深度
    4. 追问不是必须的，只在有价值时才追问

    请以标准JSON格式返回评估结果，字段如下：
    {
    "score": 整数,                        // 分数（0-100）
    "feedback": "简短客观反馈",            // 一两句话的简要评价
    "need_followup": true/false,           // 是否需要追问
    "followup_question": "追问内容，如不追问可省略或设为null", // 只有need_followup为true时必填
    "strengths": ["优点1", "优点2"],        // 回答的优点，可为空数组
    "weaknesses": ["不足1", "不足2"]        // 回答不足，可为空数组
    }

    示例1（优秀回答，不追问）：
    {
    "score": 88,
    "feedback": "回答准确全面，展现了对智能指针的深入理解，包括引用计数和线程安全等关键点",
    "need_followup": false,
    "followup_question": null,
    "strengths": ["理解了智能指针的原理", "提到了引用计数实现", "了解线程安全问题"],
    "weaknesses": ["可以进一步说明weak_ptr的应用场景"]
    }

    示例2（中等回答，需追问）：
    {
    "score": 72,
    "feedback": "理解了基本概念，但对底层实现细节掌握不够深入",
    "need_followup": true,
    "followup_question": "shared_ptr的引用计数在多线程环境下是如何保证线程安全的？",
    "strengths": ["理解了智能指针的基本用法", "提到了RAII原则"],
    "weaknesses": ["没有说明引用计数的实现", "未提及线程安全问题"]
    }

    示例3（差劲回答，不追问）：
    {
    "score": 35,
    "feedback": "回答不准确，对智能指针的理解存在明显错误，建议系统学习",
    "need_followup": false,
    "followup_question": null,
    "strengths": [],
    "weaknesses": ["概念混淆", "答非所问", "没有抓住问题重点"]
    })";

    std::string user_prompt = "面试问题：\n" + question + "\n\n候选人回答：\n" + answer +
        "\n\n请根据上述评分标准和要求进行专业、严格的评估，直接返回标准化的JSON格式，无须解释说明。";

    LOG_INFO(">>> Calling LLM: EvaluateAnswer");
    LOG_INFO("Question: {}", question);
    LOG_INFO("Answer: {}", answer);

    try {
        std::string response = SendMessage(user_prompt, system_prompt);

        // 使用utils中的JSON解析函数，仅提取大括号中的主对象
        auto eval_json = common::ParseJSONFromResponse(response, '{', '}');

        // 兼容部分LLM可能多返回内容的情况
        if (!eval_json.is_object() || eval_json.empty() || !eval_json.contains("score")) {
            LOG_ERROR("Parsed JSON is not a valid evaluation object or missing essential fields");
            throw std::runtime_error("Invalid evaluation JSON format");
        }

        LOG_INFO("Evaluation result: score={}, need_followup={}", 
                 eval_json.value("score", -1),
                 eval_json.value("need_followup", false));
        return eval_json;

    } catch (const nlohmann::json::exception& e) {
        LOG_ERROR("JSON parse error in EvaluateAnswer: {}", e.what());
        throw std::runtime_error("Failed to parse evaluation JSON: " + std::string(e.what()));
    } catch (const std::exception& e) {
        LOG_ERROR("EvaluateAnswer error: {}", e.what());
        // 返回默认评分
        nlohmann::json default_obj = {
            {"score", 50},
            {"feedback", "未能正确评估，返回默认分数。"},
            {"need_followup", false},
            {"followup_question", nullptr},
            {"strengths", nlohmann::json::array()},
            {"weaknesses", nlohmann::json::array()}
        };
        return default_obj;
    }
}

nlohmann::json LLMClient::GenerateSummary(const nlohmann::json& interview_records,
                                          const std::string& resume_text) {
    std::string system_prompt = R"(你是一位资深的C++技术面试官。请根据面试记录生成全面的面试总结和建议。

    总结要求：
    1. 综合评价候选人的技术水平
    2. 指出技术优势和薄弱环节
    3. 给出具体的学习建议
    4. 评估是否推荐录用

    请以JSON格式返回总结，包含以下字段：
    - overall_score: 总体分数（0-100）
    - summary: 总体评价（2-3段文字）
    - strengths: 技术优势列表
    - weaknesses: 薄弱环节列表
    - suggestions: 具体学习建议列表
    - recommendation: 录用建议（"强烈推荐"/"推荐"/"待考虑"/"不推荐"）
    - hiring_level: 建议级别（如"高级C++工程师"/"中级C++工程师"等）

    示例格式：
    {
    "overall_score": 75,
    "summary": "候选人具备扎实的C++基础...",
    "strengths": ["内存管理理解深入", "熟悉STL容器"],
    "weaknesses": ["多线程经验不足", "性能优化意识薄弱"],
    "suggestions": ["系统学习C++11/14/17新特性", "加强多线程编程实践"],
    "recommendation": "推荐",
    "hiring_level": "中级C++工程师"
    })";

    std::string user_prompt = "面试记录：\n" + interview_records.dump(2);

    if (!resume_text.empty()) {
        user_prompt += "\n\n候选人简历：\n" + resume_text;
    }

    user_prompt += "\n\n请生成完整的面试总结和建议，以JSON格式返回。";

    LOG_INFO(">>> Calling LLM: GenerateSummary");
    LOG_INFO("Interview records: {} questions", interview_records.size());

    std::string response = SendMessage(user_prompt, system_prompt);

    try {
        // 使用utils中的JSON解析函数
        auto summary = common::ParseJSONFromResponse(response);

        LOG_INFO("<<< Summary generated - Overall score: {}",
                 summary.value("overall_score", 0));
        return summary;

    } catch (const std::exception& e) {
        LOG_ERROR("Failed to parse summary JSON: {}", e.what());
        throw std::runtime_error("Failed to generate summary: " + std::string(e.what()));
    }
}

} // namespace services
} // namespace interview
