#include "services/realtime_client.h"
#include "common/logger.h"
#include "common/config.h"
#include "common/utils.h"
#include <boost/asio/executor_work_guard.hpp>
#include <boost/asio/ip/tcp.hpp>
#include <boost/asio/post.hpp>
#include <boost/asio/steady_timer.hpp>
#include <boost/beast/core.hpp>
#include <boost/beast/ssl.hpp>
#include <boost/beast/websocket.hpp>
#include <boost/beast/websocket/ssl.hpp>
#include <nlohmann/json.hpp>
#include <openssl/ssl.h>
#include <openssl/x509.h>

#include <atomic>
#include <cstdlib>
#include <fstream>
#include <condition_variable>
#include <deque>
#include <future>
#include <mutex>
#include <optional>
#include <thread>

namespace beast = boost::beast;
namespace websocket = beast::websocket;
namespace net = boost::asio;
namespace ssl = boost::asio::ssl;
using tcp = boost::asio::ip::tcp;

namespace interview {
namespace services {

namespace {

// 没设回调时，收到的消息最多留这么多条，满了丢最旧的
constexpr std::size_t kInboxLimit = 256;
// 丢音频的告警每丢这么多帧打一次，避免刷屏
constexpr std::uint64_t kDropLogEvery = 50;

RealtimeClientOptions OptionsFromConfig() {
    const auto& cfg = common::Config::Instance();
    RealtimeClientOptions options;
    options.tls_verify = cfg.ws_config.tls_verify;
    options.ca_file = cfg.ws_config.ca_file;
    const auto& input = cfg.input_audio_config;
    const auto bytes_per_second = static_cast<std::size_t>(input.sample_rate) *
                                  static_cast<std::size_t>(input.channels) *
                                  static_cast<std::size_t>(input.bit_size / 8);
    if (bytes_per_second > 0) {
        options.max_audio_backlog_bytes = bytes_per_second / 2;  // 约 0.5 s
    }
    return options;
}

std::string PayloadText(const common::ParsedResponse& response) {
    if (response.is_binary) {
        return std::to_string(response.payload_bytes.size()) + " binary bytes";
    }
    return response.payload.dump(-1, ' ', false, nlohmann::json::error_handler_t::replace);
}

bool IsErrorResponse(const common::ParsedResponse& response) {
    return response.message_type == "SERVER_ERROR_RESPONSE" || response.message_type == "SERVER_ERROR";
}

bool FileExists(const std::string& path) {
    return !path.empty() && std::ifstream(path).good();
}

} // namespace

std::string ResolveDefaultCaFile() {
    std::vector<std::string> candidates;
    if (const char* env = std::getenv("SSL_CERT_FILE")) {
        candidates.emplace_back(env);
    }
    candidates.emplace_back(X509_get_default_cert_file());
#ifdef __APPLE__
    // vcpkg / Homebrew 的 OpenSSL 默认路径指向它们自己的前缀，那里通常没有 CA 包；
    // macOS 系统自带一份 PEM 格式的根证书。
    candidates.emplace_back("/etc/ssl/cert.pem");
    candidates.emplace_back("/private/etc/ssl/cert.pem");
    candidates.emplace_back("/opt/homebrew/etc/ca-certificates/cert.pem");
    candidates.emplace_back("/opt/homebrew/etc/openssl@3/cert.pem");
    candidates.emplace_back("/usr/local/etc/openssl@3/cert.pem");
#endif
    for (const auto& path : candidates) {
        if (FileExists(path)) {
            return path;
        }
    }
#ifdef __APPLE__
    std::string tried;
    for (const auto& path : candidates) {
        tried += (tried.empty() ? "" : ", ") + path;
    }
    throw std::runtime_error("No CA certificate file found for TLS verification (tried " + tried +
                             "). Set ws.ca_file to a PEM bundle; verification stays on.");
#else
    return {};
#endif
}

// 连接由一个 I/O 线程独占：ws_ 的读、写、关闭只在这个线程上执行。
// 其他线程只通过 net::post 把任务投给它，所以同一时刻不会有两个线程用 ws_。
class RealtimeClient::RealtimeClientImpl {
    using WsStream = websocket::stream<beast::ssl_stream<beast::tcp_stream>>;

    enum class State { kIdle, kConnecting, kOpen, kClosing, kClosed };
    enum class CloseStep { kNone, kWaitSessionFinished, kDrain, kWsClose, kDone };

    struct Link {
        std::shared_ptr<net::io_context> ioc;
        std::string session_id;
    };

    struct Outgoing {
        std::vector<uint8_t> bytes;
        bool audio = false;
    };

public:
    RealtimeClientImpl(const std::string& url,
                       const std::map<std::string, std::string>& headers,
                       const RealtimeClientOptions& options)
        : url_(url)
        , headers_(headers)
        , opt_(options)
        , ssl_ctx_(ssl::context::tlsv12_client)
    {
        ParseUrl();
        if (opt_.tls_verify) {
            ssl_ctx_.set_verify_mode(ssl::verify_peer);
            const std::string ca_file = opt_.ca_file.empty() ? ResolveDefaultCaFile() : opt_.ca_file;
            if (ca_file.empty()) {
                ssl_ctx_.set_default_verify_paths();
            } else {
                ssl_ctx_.load_verify_file(ca_file);
                LOG_INFO("TLS CA file: {}", ca_file);
            }
        } else {
            ssl_ctx_.set_verify_mode(ssl::verify_none);
            LOG_WARNING("TLS certificate verification is off (ws.tls_verify=false)");
        }
    }

    ~RealtimeClientImpl() {
        if (OnIoThread()) {
            LOG_CRITICAL("RealtimeClient destroyed from its own response callback");
            StopIo();
            return;
        }
        try {
            Close();
        } catch (const std::exception& e) {
            LOG_ERROR("Error in RealtimeClientImpl destructor: {}", e.what());
        }
        StopIo();
    }

    // 建立 WebSocket 连接，并初始化实时会话；收到 SESSION_STARTED 才返回。
    void Connect() {
        std::lock_guard<std::mutex> lifecycle(lifecycle_mutex_);
        if (connected_) {
            LOG_WARNING("Already connected to server");
            return;
        }
        if (OnIoThread()) {
            throw std::logic_error("RealtimeClient::Connect cannot be called from the response callback");
        }
        StopIo();
        ResetConnectionState();

        auto promise = std::make_shared<std::promise<void>>();
        auto done = promise->get_future();
        connect_promise_ = promise;

        auto ioc = CurrentLink().ioc;
        io_running_ = true;
        io_thread_ = std::thread([this, ioc]() {
            io_thread_id_.store(std::this_thread::get_id());
            try {
                ioc->run();
            } catch (const std::exception& e) {
                LOG_ERROR("Realtime I/O thread stopped by exception: {}", e.what());
            }
            io_running_ = false;
            inbox_cv_.notify_all();
        });
        net::post(*ioc, [this]() { StartResolve(); });

        std::string error;
        if (done.wait_for(opt_.connect_timeout) != std::future_status::ready) {
            net::post(*ioc, [this]() { FailConnect("timed out waiting for the session to start"); });
            if (done.wait_for(std::chrono::seconds(2)) != std::future_status::ready) {
                error = "timed out waiting for the session to start";
            }
        }
        if (error.empty()) {
            try {
                done.get();
                LOG_INFO("Connected to {}", url_);
                return;
            } catch (const std::exception& e) {
                error = e.what();
            }
        }
        StopIo();
        throw std::runtime_error("Failed to connect: " + error);
    }

    // 发送麦克风录音的PCM音频数据给服务器进行ASR识别：只投递，不碰连接。
    void SendAudioData(const std::vector<uint8_t>& audio) {
        auto link = CurrentLink();
        if (!connected_ || !link.ioc) {
            throw std::runtime_error("Not connected");
        }
        auto message = common::Protocol::BuildClientAudioRequest(
            common::events::TASK_REQUEST, link.session_id, audio);
        net::post(*link.ioc, [this, m = std::move(message)]() mutable {
            EnqueueAudio(std::move(m));
        });
    }

    // 发送文本提示让AI主动说话（而不是等待用户说话触发）。
    void SendTextQuery(const std::string& text) {
        auto link = CurrentLink();
        if (!connected_ || !link.ioc) {
            throw std::runtime_error("Not connected");
        }

        std::string prompt = R"(直接朗读下面文字：)" + text + R"(后续对应于面试者的回答都只回复[好的，我们继续],不要承接或评论)";

        nlohmann::json payload;
        payload["content"] = prompt;
        auto message = common::Protocol::BuildFullRequest(
            common::events::CHAT_TEXT_QUERY, link.session_id, payload);
        net::post(*link.ioc, [this, m = std::move(message)]() mutable {
            if (state_ != State::kOpen) {
                LOG_WARNING("Dropped text query: connection is no longer open");
                return;
            }
            EnqueueControl(std::move(m));
        });
        LOG_INFO("Sent prompt query: {}", prompt);
    }

    void SendEvent(uint32_t event, const nlohmann::json& payload) {
        auto link = CurrentLink();
        if (!connected_ || !link.ioc) {
            throw std::runtime_error("Not connected");
        }
        auto message = common::Protocol::BuildFullRequest(event, link.session_id, payload);
        net::post(*link.ioc, [this, event, m = std::move(message)]() mutable {
            if (state_ != State::kOpen) {
                LOG_WARNING("Dropped event {}: connection is no longer open", event);
                return;
            }
            EnqueueControl(std::move(m));
        });
    }

    common::ParsedResponse ReceiveResponse() {
        std::unique_lock<std::mutex> lock(inbox_mutex_);
        inbox_cv_.wait(lock, [this]() { return !inbox_.empty() || !connected_; });
        if (inbox_.empty()) {
            throw std::runtime_error("Not connected");
        }
        auto response = std::move(inbox_.front());
        inbox_.pop_front();
        return response;
    }

    void SetResponseCallback(ResponseCallback callback) {
        std::lock_guard<std::mutex> lock(callback_mutex_);
        callback_ = std::move(callback);
    }

    bool IsConnected() const {
        return connected_;
    }

    RealtimeClientStats GetStats() const {
        RealtimeClientStats stats;
        stats.audio_frames_sent = audio_sent_.load();
        stats.audio_frames_dropped = audio_dropped_.load();
        stats.control_frames_sent = control_sent_.load();
        return stats;
    }

    void Close() {
        // 回调里调用：I/O 线程不能等自己，只发起关闭
        if (OnIoThread()) {
            BeginClose(true);
            return;
        }

        std::lock_guard<std::mutex> lifecycle(lifecycle_mutex_);
        auto link = CurrentLink();
        if (!io_thread_.joinable() || !link.ioc) {
            SetDisconnected();
            return;
        }

        if (io_running_) {
            auto done = std::make_shared<std::promise<void>>();
            auto finished = done->get_future();
            net::post(*link.ioc, [this, done]() {
                if (state_ == State::kClosed) {
                    done->set_value();
                    return;
                }
                close_waiters_.push_back(done);
                BeginClose(true);
            });
            // close_timeout 由 I/O 线程上的定时器兜底，这里多等 1 s 只防 I/O 线程卡在回调里
            const auto deadline = std::chrono::steady_clock::now() + opt_.close_timeout + std::chrono::seconds(1);
            while (finished.wait_for(std::chrono::milliseconds(20)) != std::future_status::ready) {
                if (!io_running_ || std::chrono::steady_clock::now() > deadline) {
                    break;
                }
            }
        }
        StopIo();
        LOG_INFO("Connection closed");
    }

private:
    // ---------------- 以下在调用方线程上执行 ----------------

    void ParseUrl() {
        // 解析URL，获取host、port、path
        size_t pos = url_.find("://");
        if (pos == std::string::npos) {
            throw std::runtime_error("Invalid URL");
        }
        std::string protocol = url_.substr(0, pos);
        if (protocol != "wss") {
            throw std::runtime_error("Unsupported protocol: " + protocol);
        }

        size_t path_pos = url_.find("/", pos + 3);
        if (path_pos == std::string::npos) {
            host_ = url_.substr(pos + 3);
            path_ = "/";
        } else {
            host_ = url_.substr(pos + 3, path_pos - (pos + 3));
            path_ = url_.substr(path_pos);
        }

        size_t port_pos = host_.find(':');
        if (port_pos != std::string::npos) {
            port_ = host_.substr(port_pos + 1);
            host_ = host_.substr(0, port_pos);
        } else {
            port_ = "443";  // 默认端口
        }
    }

    Link CurrentLink() {
        std::lock_guard<std::mutex> lock(link_mutex_);
        return Link{ioc_, session_id_};
    }

    bool OnIoThread() const {
        return io_thread_id_.load() == std::this_thread::get_id();
    }

    // 只在 I/O 线程没在跑时调用（新建连接前）
    void ResetConnectionState() {
        {
            std::lock_guard<std::mutex> lock(link_mutex_);
            ioc_ = std::make_shared<net::io_context>(1);
            session_id_ = common::GenerateUUID();
        }
        work_.emplace(net::make_work_guard(*ioc_));
        resolver_ = std::make_unique<tcp::resolver>(*ioc_);
        ws_ = std::make_unique<WsStream>(*ioc_, ssl_ctx_);
        finish_timer_ = std::make_unique<net::steady_timer>(*ioc_);
        close_timer_ = std::make_unique<net::steady_timer>(*ioc_);
        rbuf_.consume(rbuf_.size());
        control_q_.clear();
        audio_q_.clear();
        audio_q_bytes_ = 0;
        current_.clear();
        writing_ = false;
        state_ = State::kConnecting;
        close_step_ = CloseStep::kNone;
        session_started_ = false;
        session_finished_ = false;
        close_waiters_.clear();
        {
            std::lock_guard<std::mutex> lock(inbox_mutex_);
            inbox_.clear();
        }
    }

    // 停掉 I/O 线程并释放连接对象；线程退出后这些对象不再被任何线程使用
    void StopIo() {
        auto ioc = CurrentLink().ioc;
        if (ioc) {
            ioc->stop();
        }
        if (io_thread_.joinable()) {
            if (OnIoThread()) {
                // 只会在回调里析构 RealtimeClient 时发生，这是调用方的错误；线程只能放手
                io_thread_.detach();
                return;
            }
            io_thread_.join();
        }
        io_thread_id_.store(std::thread::id());
        io_running_ = false;
        SetDisconnected();
        ws_.reset();
        finish_timer_.reset();
        close_timer_.reset();
        resolver_.reset();
        work_.reset();
        state_ = State::kClosed;
    }

    // ---------------- 以下只在 I/O 线程上执行 ----------------

    void SetDisconnected() {
        {
            std::lock_guard<std::mutex> lock(inbox_mutex_);
            connected_ = false;
        }
        inbox_cv_.notify_all();
    }

    void StartResolve() {
        resolver_->async_resolve(host_, port_,
            [this](beast::error_code ec, tcp::resolver::results_type results) {
                if (ec) {
                    return FailConnect("resolve " + host_ + ": " + ec.message());
                }
                if (state_ != State::kConnecting) {
                    return;
                }
                auto& tcp_layer = beast::get_lowest_layer(*ws_);
                tcp_layer.expires_after(opt_.connect_timeout);
                tcp_layer.async_connect(results,
                    [this](beast::error_code connect_ec, tcp::resolver::results_type::endpoint_type) {
                        if (connect_ec) {
                            return FailConnect("tcp connect: " + connect_ec.message());
                        }
                        if (state_ != State::kConnecting) {
                            return;
                        }
                        StartTlsHandshake();
                    });
            });
    }

    void StartTlsHandshake() {
        SSL* ssl_handle = ws_->next_layer().native_handle();
        // 设置SNI主机名
        if (!SSL_set_tlsext_host_name(ssl_handle, host_.c_str())) {
            return FailConnect("failed to set SNI host name");
        }
        // 校验证书时同时校验主机名（X509_VERIFY_PARAM_set1_host 从 OpenSSL 1.0.2 起就有）
        if (opt_.tls_verify &&
            X509_VERIFY_PARAM_set1_host(SSL_get0_param(ssl_handle), host_.c_str(), 0) != 1) {
            return FailConnect("failed to set TLS host name check");
        }
        ws_->next_layer().async_handshake(ssl::stream_base::client, [this](beast::error_code ec) {
            if (ec) {
                std::string message = "TLS handshake: " + ec.message();
                if (opt_.tls_verify) {
                    message += " (certificate verification is on: set ws.ca_file if this machine has no CA bundle,"
                               " or ws.tls_verify=false to turn verification off)";
                }
                return FailConnect(message);
            }
            if (state_ != State::kConnecting) {
                return;
            }
            StartWebSocketHandshake();
        });
    }

    void StartWebSocketHandshake() {
        beast::get_lowest_layer(*ws_).expires_never();

        // 设置WebSocket选项：自定义header、User-Agent，模仿Python websockets
        ws_->set_option(websocket::stream_base::decorator(
            [this](websocket::request_type& req) {
                for (const auto& [key, value] : headers_) {
                    req.set(key, value);
                }
                req.set(boost::beast::http::field::user_agent, "Python/3.7 websockets/10.0");
            }
        ));
        ws_->binary(true);
        // 禁用自动分帧，确保数据包原子发送
        ws_->auto_fragment(false);
        ws_->write_buffer_bytes(16384);
        // 静默处理控制帧
        ws_->control_callback([](websocket::frame_type kind, beast::string_view payload) {
            boost::ignore_unused(kind, payload);
        });
        // 和原来一样不设空闲超时、不发 ping（模仿 Python 的 ping_interval=None，服务端不保证回 pong）；
        // 关闭卡住由 close_timeout 兜底
        websocket::stream_base::timeout timeout_opt;
        timeout_opt.handshake_timeout = opt_.connect_timeout;
        timeout_opt.idle_timeout = websocket::stream_base::none();
        timeout_opt.keep_alive_pings = false;
        ws_->set_option(timeout_opt);

        ws_->async_handshake(host_, path_, [this](beast::error_code ec) {
            if (ec) {
                return FailConnect("websocket handshake: " + ec.message());
            }
            if (state_ != State::kConnecting) {
                return;
            }
            // START_CONNECTION 不带 session_id
            WriteDuringConnect(common::Protocol::BuildFullRequest(
                common::events::START_CONNECTION, "", nlohmann::json::object()));
        });
    }

    // 建连阶段一问一答，这时还没有别的写，直接写
    void WriteDuringConnect(std::vector<uint8_t> message) {
        current_ = std::move(message);
        ws_->async_write(net::buffer(current_), [this](beast::error_code ec, std::size_t) {
            if (ec) {
                return FailConnect("send during connect: " + ec.message());
            }
            if (state_ != State::kConnecting) {
                return;
            }
            ReadDuringConnect();
        });
    }

    void ReadDuringConnect() {
        ws_->async_read(rbuf_, [this](beast::error_code ec, std::size_t) {
            if (ec) {
                return FailConnect("read during connect: " + ec.message());
            }
            if (state_ != State::kConnecting) {
                return;
            }
            OnConnectResponse(TakeResponse());
        });
    }

    void OnConnectResponse(const common::ParsedResponse& response) {
        if (IsErrorResponse(response)) {
            return FailConnect("server error " + std::to_string(response.code) + ": " + PayloadText(response));
        }
        switch (response.event) {
        case common::events::CONNECTION_STARTED: {
            LOG_INFO("Connection started, starting session");
            // payload 里带会话参数（采样率、音频格式、VAD/TTS等配置）
            auto payload = opt_.start_session.is_null()
                ? common::Config::Instance().GenerateStartSessionRequest()
                : opt_.start_session;
            WriteDuringConnect(common::Protocol::BuildFullRequest(
                common::events::START_SESSION, session_id_, payload));
            return;
        }
        case common::events::CONNECTION_FAILED:
            return FailConnect("connection failed: " + PayloadText(response));
        case common::events::SESSION_STARTED:
            session_started_ = true;
            state_ = State::kOpen;
            connected_ = true;
            if (connect_promise_) {
                connect_promise_->set_value();
                connect_promise_.reset();
            }
            Deliver(response);
            StartReadLoop();
            MaybeWrite();
            return;
        case common::events::SESSION_ENDED:
            return FailConnect("session failed: " + PayloadText(response));
        default:
            LOG_DEBUG("Ignored event {} while connecting", response.event);
            ReadDuringConnect();
            return;
        }
    }

    void FailConnect(const std::string& message) {
        if (state_ != State::kConnecting) {
            return;
        }
        LOG_ERROR("Realtime connect failed: {}", message);
        state_ = State::kClosed;
        close_step_ = CloseStep::kDone;
        SetDisconnected();
        if (connect_promise_) {
            connect_promise_->set_exception(std::make_exception_ptr(std::runtime_error(message)));
            connect_promise_.reset();
        }
        ShutdownTransport();
    }

    common::ParsedResponse TakeResponse() {
        std::vector<uint8_t> data(rbuf_.size());
        net::buffer_copy(net::buffer(data), rbuf_.data());
        rbuf_.consume(rbuf_.size());
        return common::Protocol::ParseResponse(data);
    }

    void StartReadLoop() {
        ws_->async_read(rbuf_, [this](beast::error_code ec, std::size_t) {
            if (ec) {
                return OnTransportError("read", ec);
            }
            HandleIncoming(TakeResponse());
            if (state_ == State::kOpen || state_ == State::kClosing) {
                StartReadLoop();
            }
        });
    }

    void HandleIncoming(const common::ParsedResponse& response) {
        const bool session_over = response.event == common::events::SESSION_FINISHED ||
                                  response.event == common::events::SESSION_ENDED;
        if (session_over) {
            // 先记下，回调里调 Close() 时就不会再发 FINISH_SESSION
            session_finished_ = true;
        }
        Deliver(response);
        if (!session_over) {
            return;
        }
        LOG_INFO("Session finished event: {}", response.event);
        SetDisconnected();
        if (state_ == State::kOpen) {
            // 服务端先结束了会话：照常收尾，只是不再发 FINISH_SESSION
            BeginClose(false);
        } else if (state_ == State::kClosing && close_step_ == CloseStep::kWaitSessionFinished) {
            SendFinishConnection();
        }
    }

    void Deliver(const common::ParsedResponse& response) {
        ResponseCallback callback_copy;
        {
            std::lock_guard<std::mutex> lock(callback_mutex_);
            callback_copy = callback_;
        }
        if (callback_copy) {
            try {
                callback_copy(response);
            } catch (const std::exception& e) {
                LOG_ERROR("Realtime response callback threw: {}", e.what());
            }
            return;
        }
        {
            std::lock_guard<std::mutex> lock(inbox_mutex_);
            if (inbox_.size() >= kInboxLimit) {
                inbox_.pop_front();
            }
            inbox_.push_back(response);
        }
        inbox_cv_.notify_one();
    }

    void EnqueueControl(std::vector<uint8_t> message) {
        control_q_.push_back(Outgoing{std::move(message), false});
        MaybeWrite();
    }

    void EnqueueAudio(std::vector<uint8_t> message) {
        if (state_ != State::kOpen) {
            return;
        }
        audio_q_bytes_ += message.size();
        audio_q_.push_back(std::move(message));
        // 积压超过上限就丢最旧的，延迟不会一直涨；至少留一帧
        while (audio_q_bytes_ > opt_.max_audio_backlog_bytes && audio_q_.size() > 1) {
            audio_q_bytes_ -= audio_q_.front().size();
            audio_q_.pop_front();
            const auto dropped = audio_dropped_.fetch_add(1) + 1;
            if (dropped == 1 || dropped % kDropLogEvery == 0) {
                LOG_WARNING("Realtime audio backlog over {} bytes, dropped {} oldest frames so far",
                            opt_.max_audio_backlog_bytes, dropped);
            }
        }
        MaybeWrite();
    }

    // 同一时刻只有一个 async_write 在途；控制帧优先
    void MaybeWrite() {
        if (writing_ || !(state_ == State::kOpen || state_ == State::kClosing)) {
            return;
        }
        if (close_step_ == CloseStep::kWsClose || close_step_ == CloseStep::kDone) {
            return;
        }
        bool is_audio = false;
        if (!control_q_.empty()) {
            current_ = std::move(control_q_.front().bytes);
            is_audio = control_q_.front().audio;
            control_q_.pop_front();
        } else if (!audio_q_.empty() && state_ == State::kOpen) {
            current_ = std::move(audio_q_.front());
            audio_q_bytes_ -= current_.size();
            audio_q_.pop_front();
            is_audio = true;
        } else {
            return;
        }
        writing_ = true;
        ws_->async_write(net::buffer(current_), [this, is_audio](beast::error_code ec, std::size_t) {
            writing_ = false;
            if (ec) {
                return OnTransportError("write", ec);
            }
            if (is_audio) {
                audio_sent_.fetch_add(1);
            } else {
                control_sent_.fetch_add(1);
            }
            if (state_ == State::kClosing && close_step_ == CloseStep::kDrain && control_q_.empty()) {
                return CloseWebSocket();
            }
            MaybeWrite();
        });
    }

    void OnTransportError(const char* what, const beast::error_code& ec) {
        if (state_ == State::kClosed) {
            return;
        }
        if (state_ == State::kConnecting) {
            return FailConnect(std::string(what) + ": " + ec.message());
        }
        if (state_ == State::kClosing) {
            // 关闭过程中对端先断开：算关完
            LOG_DEBUG("Connection ended during close ({}): {}", what, ec.message());
            return FinishClose();
        }
        LOG_ERROR("Realtime connection lost ({}): {}", what, ec.message());
        FinishClose();
    }

    // 关闭按固定顺序走：FINISH_SESSION → 等 SESSION_FINISHED → FINISH_CONNECTION → close，总时限兜底
    void BeginClose(bool send_finish_session) {
        if (state_ == State::kClosed) {
            NotifyCloseWaiters();
            return;
        }
        if (state_ == State::kClosing) {
            return;
        }
        if (state_ == State::kConnecting || state_ == State::kIdle) {
            FailConnect("closed while connecting");
            NotifyCloseWaiters();
            return;
        }

        LOG_INFO("Closing connection...");
        state_ = State::kClosing;
        SetDisconnected();
        // 已经排队的音频按原顺序排在 FINISH_SESSION 前面，先发完再结束会话
        for (auto& pending : audio_q_) {
            control_q_.push_back(Outgoing{std::move(pending), true});
        }
        audio_q_.clear();
        audio_q_bytes_ = 0;

        close_timer_->expires_after(opt_.close_timeout);
        close_timer_->async_wait([this](beast::error_code ec) {
            if (ec || state_ == State::kClosed) {
                return;
            }
            LOG_WARNING("Close did not finish within {} ms, closing the socket", opt_.close_timeout.count());
            FinishClose();
        });

        if (send_finish_session && session_started_ && !session_finished_) {
            close_step_ = CloseStep::kWaitSessionFinished;
            EnqueueControl(common::Protocol::BuildFullRequest(
                common::events::FINISH_SESSION, session_id_, nlohmann::json::object()));
            finish_timer_->expires_after(opt_.finish_session_wait);
            finish_timer_->async_wait([this](beast::error_code ec) {
                if (ec || state_ != State::kClosing || close_step_ != CloseStep::kWaitSessionFinished) {
                    return;
                }
                LOG_WARNING("No SESSION_FINISHED within {} ms, finishing the connection anyway",
                            opt_.finish_session_wait.count());
                SendFinishConnection();
            });
        } else {
            SendFinishConnection();
        }
    }

    void SendFinishConnection() {
        finish_timer_->cancel();
        close_step_ = CloseStep::kDrain;
        // FINISH_CONNECTION 不带 session_id；写完且控制队列为空后发 close 帧
        EnqueueControl(common::Protocol::BuildFullRequest(
            common::events::FINISH_CONNECTION, "", nlohmann::json::object()));
    }

    void CloseWebSocket() {
        close_step_ = CloseStep::kWsClose;
        ws_->async_close(websocket::close_code::normal, [this](beast::error_code ec) {
            if (ec && ec != net::error::operation_aborted) {
                LOG_DEBUG("WebSocket close: {}", ec.message());
            }
            FinishClose();
        });
    }

    void FinishClose() {
        if (state_ == State::kClosed && close_step_ == CloseStep::kDone) {
            return;
        }
        close_step_ = CloseStep::kDone;
        state_ = State::kClosed;
        SetDisconnected();
        control_q_.clear();
        audio_q_.clear();
        audio_q_bytes_ = 0;
        ShutdownTransport();
        NotifyCloseWaiters();
    }

    // 取消所有挂着的操作并关 socket；没有活以后 io_context 自然退出
    void ShutdownTransport() {
        if (finish_timer_) {
            finish_timer_->cancel();
        }
        if (close_timer_) {
            close_timer_->cancel();
        }
        if (resolver_) {
            resolver_->cancel();
        }
        if (ws_) {
            beast::get_lowest_layer(*ws_).close();
        }
        work_.reset();
    }

    void NotifyCloseWaiters() {
        for (auto& waiter : close_waiters_) {
            waiter->set_value();
        }
        close_waiters_.clear();
    }

private:
    std::string url_;
    std::string host_;
    std::string port_;
    std::string path_;
    std::map<std::string, std::string> headers_;
    RealtimeClientOptions opt_;
    ssl::context ssl_ctx_;

    std::mutex lifecycle_mutex_;   // 串行化外部线程的 Connect / Close
    std::mutex link_mutex_;        // 保护 ioc_ 和 session_id_ 的替换
    std::shared_ptr<net::io_context> ioc_;
    std::string session_id_;
    std::thread io_thread_;
    std::atomic<std::thread::id> io_thread_id_{};
    std::atomic<bool> io_running_{false};
    std::atomic<bool> connected_{false};

    // 以下只在 I/O 线程上访问（新建连接前、线程退出后由调用方线程重置）
    std::optional<net::executor_work_guard<net::io_context::executor_type>> work_;
    std::unique_ptr<tcp::resolver> resolver_;
    std::unique_ptr<WsStream> ws_;
    std::unique_ptr<net::steady_timer> finish_timer_;
    std::unique_ptr<net::steady_timer> close_timer_;
    beast::flat_buffer rbuf_;
    std::deque<Outgoing> control_q_;   // 控制帧，关闭时也装着待发完的音频
    std::deque<std::vector<uint8_t>> audio_q_;
    std::size_t audio_q_bytes_ = 0;
    std::vector<uint8_t> current_;   // 正在写的那一帧，写完前不能动
    bool writing_ = false;
    State state_ = State::kIdle;
    CloseStep close_step_ = CloseStep::kNone;
    bool session_started_ = false;
    bool session_finished_ = false;
    std::shared_ptr<std::promise<void>> connect_promise_;
    std::vector<std::shared_ptr<std::promise<void>>> close_waiters_;

    std::atomic<std::uint64_t> audio_sent_{0};
    std::atomic<std::uint64_t> audio_dropped_{0};
    std::atomic<std::uint64_t> control_sent_{0};

    std::mutex callback_mutex_;
    // 把服务端消息抛给上层业务的回调，在 I/O 线程上执行
    ResponseCallback callback_;

    std::mutex inbox_mutex_;
    std::condition_variable inbox_cv_;
    std::deque<common::ParsedResponse> inbox_;   // 没设回调时的收件箱
};

RealtimeClient::RealtimeClient(const std::string& url,
                               const std::map<std::string, std::string>& headers)
    : pimpl_(std::make_unique<RealtimeClientImpl>(url, headers, OptionsFromConfig())) {
}

RealtimeClient::RealtimeClient(const std::string& url,
                               const std::map<std::string, std::string>& headers,
                               const RealtimeClientOptions& options)
    : pimpl_(std::make_unique<RealtimeClientImpl>(url, headers, options)) {
}

RealtimeClient::~RealtimeClient() = default;

void RealtimeClient::Connect() {
    pimpl_->Connect();
}

void RealtimeClient::SendAudioData(const std::vector<uint8_t>& audio) {
    pimpl_->SendAudioData(audio);
}

void RealtimeClient::SendTextQuery(const std::string& text) {
    pimpl_->SendTextQuery(text);
}

void RealtimeClient::SendEvent(uint32_t event, const nlohmann::json& payload) {
    pimpl_->SendEvent(event, payload);
}

common::ParsedResponse RealtimeClient::ReceiveResponse() {
    return pimpl_->ReceiveResponse();
}

RealtimeClientStats RealtimeClient::GetStats() const {
    return pimpl_->GetStats();
}

void RealtimeClient::SetResponseCallback(ResponseCallback callback) {
    pimpl_->SetResponseCallback(std::move(callback));
}

bool RealtimeClient::IsConnected() const {
    return pimpl_->IsConnected();
}

void RealtimeClient::Close() {
    pimpl_->Close();
}

} // namespace services
} // namespace interview
