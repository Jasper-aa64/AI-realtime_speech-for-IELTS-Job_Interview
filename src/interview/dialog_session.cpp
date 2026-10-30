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
#include <cstring>
#include <cstdint>
#include <atomic>
#include <algorithm>

namespace interview {
namespace session {

namespace {

// 单调毫秒时间戳，供延迟计时使用（与墙钟无关，不受系统时间调整影响）。
int64_t NowMs() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
               std::chrono::steady_clock::now().time_since_epoch())
        .count();
}

} // namespace

class DialogSession::DialogSessionImpl {
public:
    std::unique_ptr<services::AudioDeviceManager> audio_manager;
    std::unique_ptr<services::RealtimeClient> realtime_client;
    std::shared_ptr<InterviewSession> interview_session;

    // 流程状态
    bool is_intro_done;             // 开场阶段是否结束
    std::atomic<bool> is_running;   // 整个会话是否在运行
    std::atomic<bool> is_playing_audio; // 当前是否在播放 TTS
    std::atomic<int>  tts_cnt;

    // 暂存候选人最新待处理回答
    std::string pending_answer;
    std::mutex  pending_answer_mutex;

    // 两段延迟计时（转发包第3组数字）：
    //   段1 = 用户停下说话 → 服务端判定说完（含 end_smooth_window_ms 等待）
    //   段2 = 服务端判定说完 → 最终转写推到界面
    std::atomic<int64_t> user_start_at_ms{0};        // USER_START_SPEAKING 到达时间
    std::atomic<int64_t> last_voice_chunk_at_ms{0};  // 最近一次非静音麦克风数据发出的时间
    std::atomic<int64_t> user_stop_at_ms{0};         // USER_STOP_SPEAKING 到达时间
    std::atomic<int64_t> final_asr_display_at_ms{0}; // 最终转写推到界面的时间

    // 保存最终总结文本
    std::string final_summary;
    std::mutex  final_summary_mutex;

    // 对话内容回调
    DialogSession::DialogContentCallback dialog_content_callback;

    std::thread microphone_thread; // 采集麦克风音频的工作线程
    std::thread playback_thread;   // 播放 TTS 音频的工作线程

    std::queue<std::vector<float>> audio_queue; // TTS 音频播放队列
    std::mutex             audio_queue_mutex;
    std::condition_variable audio_queue_cv;

    DialogSessionImpl(const std::string& name)
        : is_intro_done(false)
        , is_running(false)
        , is_playing_audio(false)
        , tts_cnt(0) {
        interview_session = std::make_shared<InterviewSession>(name);
        common::InterviewStateMachine::Instance().Reset();
    }

    ~DialogSessionImpl() {
        Stop();
    }

    void TransitionToState(common::InterviewState new_state) {
        common::InterviewStateMachine::Instance().SetState(new_state);
        LOG_INFO("状态: %s", common::InterviewStateMachine::GetStateName(new_state));
    }

    // 开始对话：建立 WebSocket 连接，启动音频线程，发送开场白
    void Start() {
        if (is_running) {
            LOG_WARNING("Session already running");
            return;
        }

        auto& cfg = common::Config::Instance();

        services::AudioConfig input_cfg;
        input_cfg.sample_rate = cfg.input_audio_config.sample_rate;
        input_cfg.channels    = cfg.input_audio_config.channels;
        input_cfg.chunk       = cfg.input_audio_config.chunk;

        services::AudioConfig output_cfg;
        output_cfg.sample_rate = cfg.output_audio_config.sample_rate;
        output_cfg.channels    = cfg.output_audio_config.channels;
        output_cfg.chunk       = cfg.output_audio_config.chunk;

        audio_manager   = std::make_unique<services::AudioDeviceManager>(input_cfg, output_cfg);
        realtime_client = std::make_unique<services::RealtimeClient>(cfg.ws_config.base_url, cfg.ws_config.headers);

        realtime_client->SetResponseCallback([this](const common::ParsedResponse& response) {
            HandleServerResponse(response);
        });

        LOG_INFO("Connecting to server...");
        TransitionToState(common::InterviewState::kConnecting);
        realtime_client->Connect();

        std::this_thread::sleep_for(common::timing::CONNECTION_STABILIZE_DELAY);

        LOG_INFO("Opening audio streams...");
        audio_manager->OpenInputStream();
        audio_manager->OpenOutputStream();

        is_running = true;

        // 播放线程先启动，确保 TTS 音频队列消费者就绪
        playback_thread   = std::thread([this]() { PlaybackThreadFunc(); });
        // 麦克风线程后启动，确保 TTS 音频队列生产者就绪
        microphone_thread = std::thread([this]() { MicrophoneThreadFunc(); });

        is_playing_audio = true;

        if (dialog_content_callback) {
            dialog_content_callback("interviewer", "你好，欢迎参加今天的面试，先做一个简单的自我介绍。", 0);
        }
        std::string intro = interview_session->GetIntroPrompt();
        SendInterviewerPrompt(intro);

        LOG_INFO("Dialog session started");
    }

    // 停止对话：关闭线程、音频流、WebSocket，保存报告
    void Stop() {
        if (!is_running) {
            return;
        }

        LOG_INFO("Stopping dialog session");
        is_running = false;
        audio_queue_cv.notify_all();

        if (microphone_thread.joinable()) microphone_thread.join();
        if (playback_thread.joinable())   playback_thread.join();

        // 先关 WebSocket，再清理音频（顺序与参考一致）
        if (realtime_client) realtime_client->Close();
        if (audio_manager)   audio_manager->Cleanup();

        if (interview_session) {
            try {
                std::string report_file = interview_session->SaveReport();
                LOG_INFO("Interview report saved: {}", report_file);
            } catch (const std::exception& e) {
                LOG_ERROR("Failed to save report: {}", e.what());
            }
        }

        if (interview_session) {
            std::string summary_copy;
            {
                std::lock_guard<std::mutex> lk(final_summary_mutex);
                summary_copy = final_summary;
            }

            if (summary_copy.empty() && interview_session) {
                try {
                    summary_copy = interview_session->GenerateSummary();
                    if (!summary_copy.empty()) {
                        std::lock_guard<std::mutex> lk(final_summary_mutex);
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

    // 处理服务器推送：音频包入队，事件分发给 HandleEvent
    void HandleServerResponse(const common::ParsedResponse& response) {
        
        if (response.message_type == "SERVER_ACK" && !response.payload_bytes.empty()) {
            // TTS 音频（Float32 PCM）入播放队列
            const size_t byte_count = response.payload_bytes.size();
            if (byte_count % sizeof(float) != 0) {
                LOG_WARNING("忽略异常音频包：payload 字节数({})不是 float32 对齐", byte_count);
                return;
            }
            const size_t float_count = byte_count / sizeof(float);
            std::vector<float> audio_float(float_count);
            std::memcpy(audio_float.data(), response.payload_bytes.data(), byte_count);
            {
                std::lock_guard<std::mutex> lock(audio_queue_mutex);
                audio_queue.push(audio_float);
            }
            audio_queue_cv.notify_one();
            return;
        }

        if (response.message_type == "SERVER_FULL_RESPONSE") {
            HandleEvent(response.event, response.payload);
        } else if (response.message_type == "SERVER_ERROR_RESPONSE" || response.message_type == "SERVER_ERROR") {
            LOG_ERROR("========================================");
            LOG_ERROR("[服务器错误]");
            LOG_ERROR("错误码: {}", response.code);
            LOG_ERROR("错误详情: {}", response.payload.dump(2));
            LOG_ERROR("========================================");

            // tts_cnt==0 时服务端不会再推 TTS，直接切换到空闲
            if (is_playing_audio && tts_cnt == 0) {
                LOG_WARNING("服务器错误导致无法播放 TTS，切换到空闲状态");
                is_playing_audio = false;
            }
        } else {
            LOG_WARNING("Received unexpected message type: {}", response.message_type);
        }
    }

    void HandleEvent(int event, const nlohmann::json& payload) {
        // TTS_START：面试官开始说话
        if (event == common::events::TTS_START) {
            tts_cnt++;
            is_playing_audio = true;
            // kSessionEnding 期间的总结 TTS 不改变状态，保持 kSessionEnding
            auto cur = common::InterviewStateMachine::Instance().GetState();
            if (cur != common::InterviewState::kSessionEnding) {
                TransitionToState(common::InterviewState::kInterviewerSpeaking);
            }
        }
        // TTS_END：一段 TTS 结束（队列里可能还有数据，状态切换由播放线程负责）
        else if (event == common::events::TTS_END) {
            if (tts_cnt > 0) tts_cnt--;
            LOG_DEBUG("TTS_END received, tts_cnt now: {}", tts_cnt.load());
        }
        // USER_START_SPEAKING：候选人开始说话
        else if (event == common::events::USER_START_SPEAKING) {
            if (is_playing_audio) {
                LOG_WARNING("[忽略] USER_START_SPEAKING during TTS playback (likely false trigger)");
                return;
            }
            TransitionToState(common::InterviewState::kCandidateSpeaking);
            // 新一段回答开始：记录起点，并清掉上一段的最终转写显示时间
            user_start_at_ms = NowMs();
            final_asr_display_at_ms = 0;
            // 候选人抢话：立即清空 TTS 队列并重置计数
            {
                std::lock_guard<std::mutex> lock(audio_queue_mutex);
                while (!audio_queue.empty()) audio_queue.pop();
            }
            tts_cnt = 0;
        }
        // ASR_RESULT：识别结果
        else if (event == common::events::ASR_RESULT && !payload.empty()) {
            auto cur = common::InterviewStateMachine::Instance().GetState();
            if (is_playing_audio || cur == common::InterviewState::kSessionEnding) {
                LOG_DEBUG("[忽略] ASR_RESULT (playing={} state={})", is_playing_audio.load(),
                          common::InterviewStateMachine::GetStateName(cur));
                return;
            }
            auto results = payload.value("results", nlohmann::json::array());
            if (!results.empty()) {
                auto result = results[0];
                bool is_final = !result.value("is_interim", true);
                std::string text = result.value("text", std::string());

                if (is_final) {
                    if (dialog_content_callback) {
                        int qidx = interview_session ? interview_session->GetCurrentQuestionIndex() + 1 : 1;
                        dialog_content_callback("candidate", text, qidx);
                    }
                    final_asr_display_at_ms = NowMs();
                    // 服务端先判定说完、最终转写后到（少见顺序）：段2 以转写显示为终点补记
                    int64_t stop_at = user_stop_at_ms.load();
                    if (stop_at > 0) {
                        LOG_INFO("[延迟两段报告] 段2 判定说完→界面显示: {} ms",
                                 final_asr_display_at_ms.load() - stop_at);
                    }
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
        // USER_STOP_SPEAKING：候选人说完
        else if (event == common::events::USER_STOP_SPEAKING) {
            if (is_playing_audio) {
                LOG_WARNING("[忽略] USER_STOP_SPEAKING during TTS playback (likely false trigger)");
                return;
            }
            TransitionToState(common::InterviewState::kInterviewerThinking);
            LOG_INFO("[候选人说话结束]");

            // 两段延迟报告：
            //   段1 = 最后一次非静音音频发出 → USER_STOP_SPEAKING（服务端判定说完）
            //   段2 = USER_STOP_SPEAKING → 最终转写推到界面
            // 最终转写通常先于 STOP 事件到达，此时段2为0或小正数；
            // 若转写还没到（少见），段2记 -1，由 ASR_RESULT 分支补记。
            user_stop_at_ms = NowMs();
            int64_t start_at   = user_start_at_ms.load();
            int64_t voice_at   = last_voice_chunk_at_ms.load();
            int64_t display_at = final_asr_display_at_ms.load();
            int64_t seg1 = (start_at > 0 && voice_at >= start_at)
                               ? std::max<int64_t>(0, user_stop_at_ms.load() - voice_at)
                               : -1;
            int64_t seg2 = (start_at > 0 && display_at >= start_at)
                               ? std::max<int64_t>(0, user_stop_at_ms.load() - display_at)
                               : -1;
            LOG_INFO("[延迟两段报告] 段1 停下→服务端判定说完: {} ms | 段2 判定说完→界面显示: {} ms",
                     seg1, seg2);
        }
        // SESSION_FINISHED/SESSION_ENDED：会话结束
        else if (event == common::events::SESSION_FINISHED || event == common::events::SESSION_ENDED) {
            LOG_INFO("Session finished event: {}", event);
            TransitionToState(common::InterviewState::kSessionEnding);
            Stop();
            TransitionToState(common::InterviewState::kCompleted);
        }
    }

    // 麦克风线程：始终读取音频（防止 PortAudio 缓冲区溢出），TTS 期间发静音
    void MicrophoneThreadFunc() {
        LOG_INFO("麦克风线程启动");
        int loop_count = 0;

        while (is_running) {
            try {
                auto t0 = std::chrono::steady_clock::now();
                auto audio_data = audio_manager->ReadAudio();
                auto t1 = std::chrono::steady_clock::now();

                // 段1 起点：用户停下说话的近似时刻 = 最后一次非静音数据从麦克风发出的时间。
                // TTS 播放期间发的是静音帧，不计入（is_playing_audio 时跳过）。
                if (!is_playing_audio) {
                    bool has_voice = false;
                    for (int16_t sample : audio_data) {
                        if (sample != 0) {
                            has_voice = true;
                            break;
                        }
                    }
                    if (has_voice) {
                        last_voice_chunk_at_ms = NowMs();
                    }
                }

                std::vector<uint8_t> audio_bytes(audio_data.size() * 2);
                if (!is_playing_audio) {
                    std::memcpy(audio_bytes.data(), audio_data.data(), audio_bytes.size());
                } else {
                    std::memset(audio_bytes.data(), 0, audio_bytes.size());
                }

                realtime_client->SendAudioData(audio_bytes);
                auto t2 = std::chrono::steady_clock::now();

                auto read_ms = std::chrono::duration_cast<std::chrono::milliseconds>(t1 - t0).count();
                auto send_ms = std::chrono::duration_cast<std::chrono::milliseconds>(t2 - t1).count();

                // 前10次 + 每50次打印一次循环耗时，帮助定位瓶颈
                if (loop_count < 10 || loop_count % 50 == 0) {
                    LOG_DEBUG("Mic loop #{}: read={}ms send={}ms", loop_count, read_ms, send_ms);
                }
                loop_count++;

                std::this_thread::sleep_for(common::timing::AUDIO_SEND_INTERVAL);

            } catch (const std::exception& e) {
                LOG_ERROR("麦克风读取失败: {}", e.what());
                std::this_thread::sleep_for(common::timing::ERROR_RETRY_DELAY);
            }
        }

        LOG_INFO("麦克风线程退出");
    }

    // 播放线程：消费 audio_queue，队列为空且 tts_cnt==0 时切换到空闲并触发下一步逻辑
    void PlaybackThreadFunc() {
        LOG_INFO("播放线程启动");

        while (is_running) {
            std::vector<float> audio_data;
            bool queue_empty = false;

            {
                std::unique_lock<std::mutex> lock(audio_queue_mutex);
                audio_queue_cv.wait_for(lock, common::timing::AUDIO_QUEUE_WAIT, [this]() {
                    return !audio_queue.empty() || !is_running;
                });

                if (!is_running) break;

                if (!audio_queue.empty()) {
                    audio_data = audio_queue.front();
                    audio_queue.pop(); 
                } else {
                    queue_empty = true; 
                }
            }

            if (!audio_data.empty()) {
                try {
                    audio_manager -> WriteAudio(audio_data);
                } catch (const std::exception& e) {
                    LOG_ERROR("音频播放失败: {}", e.what());
                }
            }

            // 队列空且无 TTS 在途 → 面试官说完，切换到空闲并处理候选人回答
            // kSessionEnding 状态下不做任何处理，由结束线程负责 Stop
            if (queue_empty && tts_cnt == 0) {
                auto cur = common::InterviewStateMachine::Instance().GetState();
                if (cur == common::InterviewState::kSessionEnding) {
                    continue;  // 总结 TTS 播完，不再切换状态
                }
                bool was_playing = is_playing_audio.exchange(false);
                if (was_playing) {
                    LOG_INFO("[面试官说完了，请候选人回答] - 麦克风已恢复录音");
                    TransitionToState(common::InterviewState::kIdle);
                }
                ProcessPendingAnswer();
            }
        }

        LOG_INFO("播放线程退出");
    }

    bool IsRunning() const { return is_running; }

    // 处理候选人回答：自我介绍 → 第一题；正式回答 → 追问/下一题/总结结束
    void ProcessPendingAnswer() {
        if (!interview_session) return;

        std::string answer_to_process;
        {
            std::lock_guard<std::mutex> lock(pending_answer_mutex);
            if (pending_answer.empty()) return;
            answer_to_process = std::move(pending_answer);
            pending_answer.clear();
        }

        if (answer_to_process.empty()) return;

        // 开场白阶段：自我介绍完毕，发第一题
        if (!is_intro_done) {
            is_intro_done = true;
            SendNextPrompt(interview_session->GetFirstQuestion());
            return;
        }

        // 记录回答并评分
        interview_session->RecordAnswer(answer_to_process);

        if (interview_session->ShouldFollowUp()) {
            SendNextPrompt(interview_session->GetFollowUpQuestion());
        } else if (!interview_session->IsComplete()) {
            SendNextPrompt(interview_session->GetNextQuestion());
        } else {
            // 所有题目问完 → 先静音麦克风防止用户继续触发 VAD
            is_playing_audio = true;
            TransitionToState(common::InterviewState::kSessionEnding);
            // 清空候选人在评分期间可能积累的新回答，防止二次触发总结
            {
                std::lock_guard<std::mutex> lock(pending_answer_mutex);
                pending_answer.clear();
            }

            // 生成总结（LLM 调用，耗时较长）
            std::string summary = interview_session->GenerateSummary();
            {
                std::lock_guard<std::mutex> lk(final_summary_mutex);
                final_summary = summary;
            }
            SendNextPrompt(summary);

            // 等 TTS 真正播完再 Stop：先等 TTS 开始（tts_cnt>0），再等 TTS 结束
            std::thread([this]() {
                // 阶段1：等待服务器返回 TTS_START（最多等 10 秒）
                for (int i = 0; i < 50 && is_running && tts_cnt == 0; i++) {
                    std::this_thread::sleep_for(std::chrono::milliseconds(200));
                }
                // 阶段2：等待 TTS 播完（队列清空 + tts_cnt 归零）
                while (is_running && (tts_cnt > 0 || !audio_queue.empty())) {
                    std::this_thread::sleep_for(std::chrono::milliseconds(200));
                }
                // 阶段3：等最后一段音频从 PortAudio 缓冲区播出
                std::this_thread::sleep_for(std::chrono::seconds(2));
                Stop();
            }).detach();
        }
    }

    // 发送面试官下一句话（提问 / 追问 / 总结）。
    // 调用前 LLM 已生成好文本，这里做三件事：
    //   1. 立即置 is_playing_audio=true，让麦克风线程改发静音帧，防止 VAD 误触发；
    //   2. 通过 dialog_content_callback 把文本推给 UI 显示；
    //   3. 把文本送给 SendInterviewerPrompt → WebSocket → 服务端 TTS 合成并流式回传音频。
    void SendNextPrompt(const std::string& prompt) {
        is_playing_audio = true;
        // 题号从 0-based 转为 1-based，仅供 UI 展示，不影响流程逻辑
        int qidx = interview_session ? interview_session->GetCurrentQuestionIndex() + 1 : 1;
        if (dialog_content_callback) {
            dialog_content_callback("interviewer", prompt, qidx);
        }
        SendInterviewerPrompt(prompt);
    }

    // 把文本包装成 CHAT_TEXT_QUERY 协议帧，通过 WebSocket 发给服务端。
    // 服务端收到后触发 TTS 合成，音频帧以 SERVER_ACK 流式回传，
    // 接收线程将其 push 进 audio_queue，由播放线程消费播出。
    void SendInterviewerPrompt(const std::string& text) {
        if (!realtime_client) {
            LOG_WARNING("Realtime client not ready, cannot send prompt");
            return;
        }
        if (text.empty()) {
            LOG_WARNING("Attempted to send empty interviewer prompt");
            return;
        }
        realtime_client->SendTextQuery(text);
    }

    void LogMultilineBlock(const std::string& title, const std::string& text) const {
        LOG_INFO("========================================");
        LOG_INFO("{}", title);
        LOG_INFO("========================================");
        std::istringstream iss(text);
        std::string line;
        while (std::getline(iss, line)) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            LOG_INFO("{}", line);
        }
        LOG_INFO("========================================");
    }
};

DialogSession::DialogSession(const std::string& candidate_name)
    : pimpl_(std::make_unique<DialogSessionImpl>(candidate_name)) {}

DialogSession::~DialogSession() = default;

void DialogSession::ConfigureResumeInterview(const std::string& resume_pdf_path, int min_questions) {
    pimpl_->interview_session->LoadQuestionsFromResume(resume_pdf_path, min_questions);
}

void DialogSession::ConfigureDefaultInterview(int min_questions) {
    pimpl_->interview_session->GenerateDefaultQuestions(min_questions);
}

void DialogSession::Start() { pimpl_->Start(); }

void DialogSession::SetDialogContentCallback(DialogContentCallback callback) {
    pimpl_->dialog_content_callback = std::move(callback);
}

void DialogSession::HandleServerResponse(const common::ParsedResponse& response) {
    pimpl_->HandleServerResponse(response);
}

void DialogSession::Stop() { pimpl_->Stop(); }

bool DialogSession::IsRunning() const { return pimpl_->IsRunning(); }

} // namespace session
} // namespace interview
