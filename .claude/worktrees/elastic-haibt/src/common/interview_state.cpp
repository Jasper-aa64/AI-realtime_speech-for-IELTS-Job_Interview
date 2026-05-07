#include "common/interview_state.h"
#include "common/logger.h"

namespace interview {
namespace common {

InterviewStateMachine::InterviewStateMachine()
    : current_state_(InterviewState::kIdle)
    , callback_(nullptr) {
    Logger::Init();
}

InterviewStateMachine& InterviewStateMachine::Instance() {
    // 返回全局单例实例
    static InterviewStateMachine instance;
    return instance;
}

InterviewState InterviewStateMachine::GetState() const {
    // 使用合适的 memory_order 读取当前状态
    return current_state_.load(std::memory_order_acquire);
}

void InterviewStateMachine::SetState(InterviewState new_state) {
    // 1) 原子更新状态并拿到 old_state
    InterviewState old_state = current_state_.load(std::memory_order_acquire);
    // 2) old_state == new_state 时直接返回
    if (old_state == new_state) {
        return;
    }
    // 3) 记录状态迁移日志（
    LOG_INFO("State transition: {} -> {}", GetStateName(old_state), GetStateName(new_state));

    current_state_.store(new_state, std::memory_order_release);
    // 4) 触发回调
    std::lock_guard<std::mutex> lock(callback_mutex_);
    if (callback_) {
        callback_(old_state, new_state);
    }

    (void)new_state;
}

void InterviewStateMachine::SetStateChangeCallback(StateChangeCallback callback) {
    //加锁后设置 callback_（多次设置可覆盖）
    std::lock_guard<std::mutex> lock(callback_mutex_);
    callback_ = callback;
}

void InterviewStateMachine::ClearStateChangeCallback() {
    // 加锁后清空 callback_
    std::lock_guard<std::mutex> lock(callback_mutex_);
    callback_ = nullptr;
}

void InterviewStateMachine::Reset() {
    // 重置到初始状态（通常是 kIdle）
    // 复用 SetState(InterviewState::kIdle)
    SetState(InterviewState::kIdle);
    LOG_INFO("State machine reset to idle");
}

const char* InterviewStateMachine::GetStateName(InterviewState state) {
    switch (state) {
        case InterviewState::kConnecting:
            return "连接中";
        case InterviewState::kInterviewerSpeaking:
            return "面试官说话中";
        case InterviewState::kIdle:
            return "空闲";
        case InterviewState::kCandidateSpeaking:
            return "候选人说话中";
        case InterviewState::kInterviewerThinking:
            return "面试官思考中";
        case InterviewState::kSessionEnding:
            return "会话结束中";
        case InterviewState::kCompleted:
            return "已完成";
        case InterviewState::kError:
            return "错误";
        default:
            return "未知状态";
    }
}

} // namespace common
} // namespace interview
