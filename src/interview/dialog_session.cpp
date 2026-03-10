#include "interview/dialog_session.h"
#include "services/audio_manager.h"
#include "services/realtime_client.h"
#include "interview/interview_manager.h"
#include "common/config.h"
#include "common/logger.h"
#include "common/interview_state.h"
#include "common/protocol.h"
#include <memory>
#include <queue>
#include <mutex>
#include <condition_variable>
#include <sstream>
#include <string>
#include <thread>
#include <chrono>

namespace interview {
namespace session {

class DialogSession::DialogSessionImpl {
public:
    std::unique_ptr<services::AudioDeviceManager> audio_manager;
    std::unique_ptr<services::RealtimeClient> realtime_client;
    std::shared_ptr<InterviewSession> interview_session;

    // 流程状态
    bool is_intro_done; // 开场阶段是否结束
    std::atomic<bool> is_running; // 整个会话是否在运行
    std::atomic<bool> is_playing_audio; // 当前是否在播放 TTS
    std::atomic<int> tts_cnt;

    // 暂存候选人最新待处理回答
    std::string pending_answer; 
    std::mutex pending_answer_mutex;

    // 保存最终总结文本
    std::string final_summary;
    std::mutex final_summary_mutex;

    // 对话内容回调
    DialogSession::DialogContentCallback dialog_content_callback;

    std::thread microphone_thread; // 采集麦克风音频的工作线程。
    std::thread playback_thread; // 播放线程

    std::queue<std::vector<float>> audio_queue; // 音频队列
    std::mutex audio_queue_mutex; 
    std::condition_variable audio_queue_cv;

    DialogSessionImpl(const std::string& name)
        : is_intro_done(false)
        , is_running(false)
        , is_playing_audio(false)
        , tts_cnt(0) {
        // 初始化面试会话实例
        interview_session = std::make_shared<InterviewSession>(name);
        // 初始化全局状态机
        common::InterviewStateMachine::Instance().Reset();
    }

    ~DialogSessionImpl() {
        Stop();
    }

    void TransitionToState(common::InterviewState new_state) {
        // 实现状态转换
        common::InterviewStateMachine::Instance().SetState(new_state);
        LOG_INFO("状态: TODO - %s", common::InterviewStateMachine::GetStateName(new_state));
    }

    void Start() {
        if (is_running) {
            LOG_WARNING("Session already running");
            return;
        }
        
        auto& cfg = common::Config::Instance();

        // 创建音频管理器
        services::AudioConfig input_cfg;
        input_cfg.sample_rate = cfg.input_audio_config.sample_rate;
        input_cfg.channels = cfg.input_audio_config.channels;
        input_cfg.chunk = cfg.input_audio_config.chunk;

        services::AudioConfig output_cfg;
        output_cfg.sample_rate = cfg.output_audio_config.sample_rate;
        output_cfg.channels = cfg.output_audio_config.channels;
        output_cfg.chunk = cfg.output_audio_config.chunk;

        audio_manager = std::make_unique<services::AudioDeviceManager>(input_cfg, output_cfg);
        
        // 创建WebSocket客户端
        realtime_client = std::make_unique<services::RealtimeClient>(cfg.ws_config.base_url, cfg.ws_config.headers);

        // 设置响应回调
        realtime_client->SetResponseCallback([this](const common::ParsedResponse& response) {
            HandleServerResponse(response);
        });

        // 连接到服务器
        LOG_INFO("Connecting to server...");
        TransitionToState(common::InterviewState::kConnecting);
        realtime_client->Connect();

        // 等待一小段时间让连接稳定
        std::this_thread::sleep_for(common::timing::CONNECTION_STABILIZE_DELAY);

        // 打开音频流
        audio_manager->OpenInputStream();
        audio_manager->OpenOutputStream();

        is_running = true;

        // 启动麦克风线程
        microphone_thread = std::thread([this]() {
            MicrophoneThreadFunc();
        });

        // 启动播放线程
        playback_thread = std::thread([this]() {
            PlaybackThreadFunc();
        });

        is_playing_audio = true;

        // 发送开场白
        if (dialog_content_callback) {
            dialog_content_callback("interviewer", "你好，欢迎参加今天的面试，先做一个简单的自我介绍。", 0);
        }
        std::string intro = interview_session->GetIntroPrompt();
        SendInterviewerPrompt(intro);

        LOG_INFO("Dialog session started");
    }

    void Stop() {
        if (!is_running) {
            return;
        }

        LOG_INFO("Stopping dialog session");
        is_running = false;
        audio_queue_cv.notify_all();

        // 等待线程结束
        if (microphone_thread.joinable()) {
            microphone_thread.join();
        }

        if (playback_thread.joinable()) {
            playback_thread.join();
        }

        // 关闭音频流
        audio_manager->Cleanup();

        // 关闭WebSocket连接
        realtime_client->Close();

        // 保存面试报告
        if (interview_session) {
            try {
                // 将报告保存为格式化的JSON文件
                std::string report_file = interview_session->SaveReport();
                LOG_INFO("Interview report saved: {}", report_file);
            } catch (const std::exception& e) {
                LOG_ERROR("Failed to save report: {}", e.what());
            }
        }

        // 生成面试总结
        if (interview_session) {
            // 读取共享字符串
            std::string summary_copy;
            {
                std::lock_guard<std::mutex> summary_lock(final_summary_mutex);
                summary_copy = final_summary;
            }

            // 缓存为空时，现场生成总结
            if (summary_copy.empty() && interview_session) {
                try {
                    summary_copy = interview_session->GenerateSummary();
                    if (!summary_copy.empty()) {
                        std::lock_guard<std::mutex> summary_lock(final_summary_mutex);
                        final_summary = summary_copy;
                    }
                } catch (const std::exception& e) {
                    LOG_ERROR("Failed to generate summary during shutdown: {}", e.what());
                }
            }

            if (!summary_copy.empty()) {
                LogMultilineBlock("[面试总结回顾]", summary_copy);
            }
        }

        LOG_INFO("Dialog session stopped");
    }

    // 处理服务器响应
    void HandleServerResponse(const common::ParsedResponse& response) {
            // 1. SERVER_ACK：协议里 SERVER_ACK 常用于服务端确认包
            // 2. 确保这条 ACK 里确实有二进制 payload；没有 payload 的 ACK 或 JSON ACK 不应按音频处理。
        if (response.message_type == "SERVER_ACK" && !response.payload_bytes.empty()) {
            // 服务器返回的PCM格式是Float32
            size_t float_count = response.payload_bytes.size() / sizeof(float);
            const float* float_data = reinterpret_cast<const float*>(response.payload_bytes.data());

            std::vector<float> audio_float(float_data, float_data + float_count);

            // LOG_DEBUG("Received audio: {} bytes = {} float32 samples", response.payload_bytes.size(), float_count);

            // 加入播放队列
            {
                std::lock_guard<std::mutex> lock(audio_queue_mutex);
                audio_queue.push(audio_float);
            }
            audio_queue_cv.notify_one();
            return;
        }

        // 服务器事件
            // 3. SERVER_FULL_RESPONSE：服务器完整响应，包含JSON payload
        if (response.message_type == "SERVER_FULL_RESPONSE") {
            HandleEvent(response.event, response.payload);
        } else if (response.message_type == "SERVER_ERROR_RESPONSE" || response.message_type == "SERVER_ERROR") {
            // 4. SERVER_ERROR_RESPONSE：服务器错误响应，包含错误码和错误消息
            // 5. SERVER_ERROR：服务器错误响应，包含错误码和错误消息
            LOG_ERROR("========================================");
            LOG_ERROR("[服务器错误]");
            LOG_ERROR("错误码: {}", response.code);
            LOG_ERROR("错误详情: {}", response.payload.dump(2));
            LOG_ERROR("========================================");

            // 服务器错误时，如果正在等待TTS响应，切换到空闲状态
            if (is_playing_audio && tts_cnt > 0) {
                LOG_WARNING("服务器错误导致无法播放TTS，切换到空闲状态");
                is_playing_audio = false;
                TransitionToState(common::InterviewState::kIdle);
            }
        } else {
            // 未知服务器响应类型
            LOG_ERROR("Unknown server response message type: {}", response.message_type);
        }
    }

    void HandleEvent(int event, const nlohmann::json& payload) {
        // Event TTS_START: TTS开始
        if (event == common::events::TTS_START) {
            tts_cnt++;
            is_playing_audio = true;
            TransitionToState(common::InterviewState::kInterviewerSpeaking);
        }
        // Event TTS_END: TTS结束
        if (event == common::events::TTS_END) {
            tts_cnt--;
            // 注意：不要在这里立即切换到 kIdle 状态
            // 因为音频队列中可能还有数据在播放
            // 状态切换应该在 PlaybackThreadFunc 中音频队列真正为空时处理
            LOG_DEBUG("TTS_END received, tts_cnt now: {}", tts_cnt.load());
        }
        // Event USER_START_SPEAKING: 用户开始说话
        if (event == common::events::USER_START_SPEAKING) {
            // 如果面试官正在说话，忽略此事件（可能是误触发）
            if (is_playing_audio ) {
                LOG_DEBUG("[忽略] USER_START_SPEAKING received, but interviewer is speaking, ignoring");
                return;
            }

            TransitionToState(common::InterviewState::kCandidateSpeaking);

            // 清队列 + tts_cnt=0  ，强制切断旧 TTS ，系统立刻进入“候选人说话优先”
            {
                std::lock_guard<std::mutex> lock(audio_queue_mutex);
                while (!audio_queue.empty()) { // 清空播放队列
                    audio_queue.pop();
                }
            }
            tts_cnt = 0; // 强制重置计数器，立即结束TTS状态
        }

        // Event ASR_RESULT: ASR识别结果
        else if (event == common::events::ASR_RESULT && !payload.empty()) {
            // 如果面试官正在说话，忽略ASR结果（应该是静音数据的误识别）
            if (is_playing_audio) {
                LOG_DEBUG("[忽略] ASR_RESULT received, but interviewer is speaking, ignoring");
                return;
            }

            // 处理ASR识别结果
            auto results = payload.value("results", nlohmann::json::array());
            if (!results.empty()) {
                auto result = results[0];
                bool is_final = !result.value("is_interim", true);
                std::string text = result.value("text", std::string());

                // is_final: 用户这次说话已经识别完成，正式入库并推动流程进入下一步
                if (is_final) {
                    // 回调给UI层，更新候选人回答文本
                    if (dialog_content_callback) {
                        int qidx = interview_session ? interview_session->GetCurrentQuestionIndex() + 1 : 1;
                        dialog_content_callback("candidate", text, qidx);
                    }
                    // 把这条最终回答存到待处理区，供后续评分/追问逻辑消费
                    {
                        std::lock_guard<std::mutex> lock(pending_answer_mutex);
                        pending_answer = std::move(text);
                    }
                    TransitionToState(common::InterviewState::kInterviewerThinking);
                } else {
                    LOG_DEBUG("[ASR临时结果]: {}", text);
                }
            } else {
                LOG_DEBUG("ASR_RESULT event received but results array is empty");
            }
        }

        // Event USER_STOP_SPEAKING: 用户说话结束
        else if (event == common::events::USER_STOP_SPEAKING) {
            // 如果面试官正在说话，忽略此事件（可能是误触发）
            if (is_playing_audio) {
                LOG_WARNING("[忽略] USER_STOP_SPEAKING during TTS playback (likely false trigger)");
                return;
            }
            TransitionToState(common::InterviewState::kInterviewerThinking);
            LOG_INFO("[候选人说话结束]");
        }
        // Event SESSION_FINISHED/SESSION_ENDED: 会话结束
        else if (event == common::events::SESSION_FINISHED || event == common::events::SESSION_ENDED) {
            LOG_INFO("Session finished event: {}", event);
            TransitionToState(common::InterviewState::kSessionEnding);
            Stop();
            TransitionToState(common::InterviewState::kCompleted);
            LOG_INFO("会话结束");
        }
    }

    void MicrophoneThreadFunc() {
        LOG_INFO("麦克风线程启动");

        // 获取配置
        auto& cfg = common::Config::Instance();
        const int chunk_size = cfg.input_audio_config.chunk; // 每次读取的采样点数
        const int sample_rate = cfg.input_audio_config.sample_rate; // 采样率

        // 计算发送间隔对应的采样点数（10ms）
        const int send_interval_ms = 10;
        const size_t samples_per_interval = static_cast<size_t>(sample_rate) * send_interval_ms / 1000; // 160 samples @16kHz

        // 缓冲区用于累积音频数据
        std::vector<int16_t> accumulated_buffer;
        accumulated_buffer.reserve(chunk_size * 2); // 预留足够空间

        while (is_running) {
            // 面试官说话期间持续发送静音包，避免服务端因长时间无音频输入而超时
            if (is_playing_audio) {
                std::vector<uint8_t> silent_audio(samples_per_interval * sizeof(int16_t), 0);
                if (realtime_client) {
                    realtime_client->SendAudioData(silent_audio);
                }
                accumulated_buffer.clear();
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                continue;
            }

            try {
                // 从音频管理器读取一个chunk（阻塞读取，约200ms的数据）
                std::vector<int16_t> audio_data = audio_manager->ReadAudio();

                // 将读取的数据添加到累积缓冲区
                accumulated_buffer.insert(accumulated_buffer.end(),
                                         audio_data.begin(), audio_data.end());

                // 当累积缓冲区有足够的数据时，发送给服务器
                while (accumulated_buffer.size() >= samples_per_interval && is_running) {
                    // 如果面试官开始说话，停止发送并清空缓冲区
                    if (is_playing_audio) {
                        accumulated_buffer.clear();
                        break;
                    }

                    // 提取一个间隔的数据
                    std::vector<int16_t> send_chunk(
                        accumulated_buffer.begin(),
                        accumulated_buffer.begin() + samples_per_interval
                    );

                    // 将int16_t转换为uint8_t（小端序）
                    std::vector<uint8_t> audio_bytes;
                    audio_bytes.reserve(send_chunk.size() * sizeof(int16_t));

                    for (int16_t sample : send_chunk) {
                        // 小端序：低字节在前
                        audio_bytes.push_back(static_cast<uint8_t>(sample & 0xFF));
                        audio_bytes.push_back(static_cast<uint8_t>((sample >> 8) & 0xFF));
                    }

                    // 发送给服务器
                    if (realtime_client) {
                        realtime_client->SendAudioData(audio_bytes);
                    }

                    // 从累积缓冲区中移除已发送的数据
                    accumulated_buffer.erase(
                        accumulated_buffer.begin(),
                        accumulated_buffer.begin() + samples_per_interval
                    );

                    // 等待下一个发送间隔
                    std::this_thread::sleep_for(std::chrono::milliseconds(send_interval_ms));
                }

            } catch (const std::exception& e) {
                LOG_ERROR("麦克风读取失败: {}", e.what());
                // 发生错误时等待一段时间后重试
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
            }
        }

        LOG_INFO("麦克风线程退出");
    }

    void PlaybackThreadFunc() {
        LOG_INFO("播放线程启动");

        while (is_running) {
            std::vector<float> audio_data;

            // 等待音频数据或超时
            {
                std::unique_lock<std::mutex> lock(audio_queue_mutex);
                if (audio_queue_cv.wait_for(lock, common::timing::AUDIO_QUEUE_WAIT, [this] {
                     return !audio_queue.empty() || !is_running; })) 
                {
                    if (!is_running) {
                        break;
                    }
                    if (!audio_queue.empty()) {
                        audio_data = std::move(audio_queue.front());
                        audio_queue.pop();
                    }
                } else {
                    // 超时，检查是否应该结束播放状态
                    if (tts_cnt == 0 && is_playing_audio) {
                        LOG_DEBUG("音频队列超时且无待播放TTS，切换到空闲状态");
                        is_playing_audio = false;
                        TransitionToState(common::InterviewState::kIdle);
                    }
                    continue;
                }
            }

            // 播放音频数据
            if (!audio_data.empty() && audio_manager) {
                try {
                    audio_manager->WriteAudio(audio_data);
                } catch (const std::exception& e) {
                    LOG_ERROR("音频播放失败: {}", e.what());
                }
            }

            // 检查是否还有待播放数据
            {
                std::lock_guard<std::mutex> lock(audio_queue_mutex);
                if (audio_queue.empty() && tts_cnt == 0 && is_playing_audio) {
                    LOG_DEBUG("音频队列已空且无待播放TTS，切换到空闲状态");
                    is_playing_audio = false;
                    TransitionToState(common::InterviewState::kIdle);
                }
            }
        }

        LOG_INFO("播放线程退出");
    }

    bool IsRunning() const {
        return is_running;
    }

    // 把“候选人刚说完的一段话”变成“追问 / 下一题 / 总结并结束” 三选一动作，并处理了开场白到正式问答的切换
    void ProcessPendingAnswer() {
        if (!interview_session) {
            return;
        }

        std::string answer_to_process;
        {
            std::lock_guard<std::mutex> lock(pending_answer_mutex);
            answer_to_process = std::move(pending_answer);
        }

        if (answer_to_process.empty()) {
            return;
        }

        // 处理开场白后的自我介绍
        if (!is_intro_done) {
            is_intro_done = true;
            std::string prompt = interview_session->GetFirstQuestion();
            SendNextPrompt(prompt);
            return;
        }

        // 记录回答并评分
        interview_session->RecordAnswer(answer_to_process);

        // 判断是否需要追问
        std::string next_prompt;
        if (interview_session->ShouldFollowUp()) {
            next_prompt = interview_session->GetFollowUpQuestion();
        }
        else if (interview_session->IsComplete()) {
            next_prompt = interview_session->GetNextQuestion();
        }
        else {
            std::string summary = interview_session->GenerateSummary();
            {
                std::lock_guard<std::mutex> lock(final_summary_mutex);
                final_summary = summary;
                SendNextPrompt(summary);
                TransitionToState(common::InterviewState::kIdle);
                // 保证总结说完后停止 因为语音异步，所以这里延迟一段时间后停止
                std::this_thread::sleep_for(common::timing::INTERVIEW_END_DELAY);
                Stop();
                return;
            }
        }

        SendNextPrompt(next_prompt);
    }

    void SendNextPrompt(const std::string& prompt) {
        is_playing_audio = true;
        // 计算当前题号（给 UI 展示用）
        int qidx = interview_session ? interview_session->GetCurrentQuestionIndex() + 1 : 1;
        // 把这句面试官文本先通知给上层
        if (dialog_content_callback) {
            dialog_content_callback("interviewer", prompt, qidx);
        }
        // 见下面
        SendInterviewerPrompt(prompt);
    }

    // 把 prompt 发给服务端，触发 TTS/语音链路 （说话！）
    void SendInterviewerPrompt(const std::string& text) {
        if (!realtime_client) {
            LOG_WARNING("Realtime client not ready, cannot send prompt");
            return;
        }
        if (text.empty()) {
            LOG_WARNING("Attempted to send empty interviewer prompt");
            return;
        }
        
        // 再发送到服务器进行TTS
        realtime_client->SendTextQuery(text);
    }

    void LogMultilineBlock(const std::string& title, const std::string& text) const {
        LOG_INFO("========================================");
        LOG_INFO("{}", title);
        LOG_INFO("========================================");

        std::istringstream iss(text);
        std::string line;
        while (std::getline(iss, line)) {
            if (!line.empty() && line.back() == '\r') {
                line.pop_back();
            }
            LOG_INFO("{}", line);
        }

        LOG_INFO("========================================");
    }
};

DialogSession::DialogSession(const std::string& candidate_name)
    : pimpl_(std::make_unique<DialogSessionImpl>(candidate_name)) {}

DialogSession::~DialogSession() = default;

// 配置简历驱动面试
void DialogSession::ConfigureResumeInterview(const std::string& resume_pdf_path, int min_questions) {
    pimpl_->interview_session->LoadQuestionsFromResume(resume_pdf_path, min_questions);
}

// 配置默认面试
void DialogSession::ConfigureDefaultInterview(int min_questions) {
    pimpl_->interview_session->GenerateDefaultQuestions(min_questions);
}

void DialogSession::Start() {
    pimpl_->Start();
}

void DialogSession::SetDialogContentCallback(DialogContentCallback callback) {
    pimpl_->dialog_content_callback = std::move(callback);
}

void DialogSession::HandleServerResponse(const common::ParsedResponse& response) {
    pimpl_->HandleServerResponse(response);
}

void DialogSession::Stop() {
    pimpl_->Stop();
}

bool DialogSession::IsRunning() const {
    return pimpl_->IsRunning();
}

} // namespace session
} // namespace interview