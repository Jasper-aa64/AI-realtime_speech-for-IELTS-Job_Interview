#include "services/realtime_client.h"
#include "common/logger.h"
#include "common/config.h"
#include "common/utils.h"
#include <boost/beast/core.hpp>
#include <boost/beast/websocket.hpp>
#include <boost/beast/ssl.hpp>
#include <boost/asio/connect.hpp>
#include <boost/asio/ip/tcp.hpp>
#include <boost/asio/ssl/stream.hpp>
#include <nlohmann/json.hpp>
#include <thread>

#include <mutex>
#include <atomic>

namespace beast = boost::beast;
// namespace http = beast::http;
namespace websocket = beast::websocket;
namespace net = boost::asio;
namespace ssl = boost::asio::ssl;
using tcp = boost::asio::ip::tcp;

namespace interview {
namespace services {


class RealtimeClient::RealtimeClientImpl {
public:
    RealtimeClientImpl(const std::string& url, const std::map<std::string, std::string>& headers)
        : url_(url)
        , headers_(headers)
        , ioc_()
        , ssl_ctx_(ssl::context::tlsv12_client)
        , resolver_(ioc_)
        , ws_(nullptr)
        , connected_(false)
        , running_(false)
    {
        // 配置SSL上下文
        ssl_ctx_.set_default_verify_paths();
        ssl_ctx_.set_verify_mode(ssl::verify_none); 

        ParseUrl();
    }

    ~RealtimeClientImpl() {
        try {
            Close();
        } catch (const std::exception& e) {
            LOG_ERROR("Error in RealtimeClientImpl destructor: {}", e.what());
        }
    }

    //  建立 WebSocket 连接，并初始化实时会话。
    void Connect() {
        if (connected_) {
            LOG_WARNING("Already connected to server");
            return;
        }
        
        try {
            // 解析主机和端口
            auto const results = resolver_.resolve(host_, port_);

            // 创建WebSocket SSL流
            //三层嵌套的通信对象：
                // 最里面：tcp::socket
                // 外面包一层：ssl_stream
                // 最外面：websocket::stream
            ws_ = std::make_unique<websocket::stream<beast::ssl_stream<tcp::socket>>>(ioc_, ssl_ctx_);

            // 设置SNI主机名
            if (!SSL_set_tlsext_host_name(ws_->next_layer().native_handle(), host_.c_str())) {
                throw std::runtime_error("Failed to set SNI hostname");
            }
            // 连接到服务器
            net::connect(ws_->next_layer().next_layer(), results.begin(), results.end());

            // SSL握手
            ws_->next_layer().handshake(ssl::stream_base::client);

            // 设置WebSocket选项：自定义header、User-Agent，模仿Python websockets
            ws_->set_option(websocket::stream_base::decorator(
                [this](websocket::request_type& req) {
                    // 添加自定义头
                    for (const auto& [key, value] : headers_) {
                        req.set(key, value);
                    }
                    // 设定User-Agent
                    req.set(boost::beast::http::field::user_agent, "Python/3.7 websockets/10.0");
                }
            ));

            // 设置二进制模式
            ws_->binary(true);

            // 禁用自动分帧，确保数据包原子发送
            ws_->auto_fragment(false);

            // 设置较大写缓冲区
            ws_->write_buffer_bytes(16384);

            // 关键修复：禁用WebSocket控制帧超时，模仿Python的ping_interval=None
            ws_->control_callback([](websocket::frame_type kind, beast::string_view payload) {
                // 静默处理控制帧
                boost::ignore_unused(kind, payload);
            });

            // 指定suggested超时
            ws_->set_option(websocket::stream_base::timeout::suggested(beast::role_type::client));

            // 配置超时为“无限”（idle_timeout=0），禁用自动ping
            auto timeout_opt = websocket::stream_base::timeout();
            timeout_opt.idle_timeout = std::chrono::seconds(0); // 禁用idle timeout
            timeout_opt.handshake_timeout = std::chrono::seconds(30);
            timeout_opt.keep_alive_pings = false;
            ws_->set_option(timeout_opt);

            // WebSocket 握手（这里发 HTTP Upgrade 请求）
                // Boost.Beast 在这一步内部自动构造并发送
                // 升级完成后就是纯 WebSocket 二进制帧传输，不再有 HTTP 
            ws_->handshake(host_, path_);

            connected_ = true; 

            LOG_INFO("Connected to {}", url_);

            // 发送StartConnection请求
            SendStartConnection();

            // 发送StartSession请求
            SendStartSession();

            // 启动接收线程，异步处理服务器响应
            StartReceiveThread();

        }catch (const std::exception& e) {
            connected_ = false;
            running_ = false;
            ws_.reset();
            throw std::runtime_error(std::string("Failed to connect: ") + e.what());
        }
    }

    // 发送麦克风录音的PCM音频数据给服务器进行ASR识别。
    void SendAudioData(const std::vector<uint8_t>& audio) {
        if (!connected_) {
            throw std::runtime_error("Not connected");
        }

        try {
            // 构建TaskRequest
            auto message = common::Protocol::BuildClientAudioRequest(
                common::events::TASK_REQUEST,
                session_id_,
                audio
            );

            // 直接写入vector数据
            ws_->write(net::buffer(message));

        } catch (const std::exception& e) {
            LOG_ERROR("Failed to send audio: {}", e.what());
            throw;
        }
    }

    // 发送文本提示让AI主动说话（而不是等待用户说话触发）。
    void SendTextQuery(const std::string& text) {
        if (!connected_) {
            throw std::runtime_error("Not connected");
        }

        std::string prompt = R"(直接朗读下面文字：)" + text + R"(后续对应于面试者的回答都只回复[好的，我们继续],不要承接或评论)";

        try {
            // 1. 构造要发送的数据 JSON
            nlohmann::json payload;
            payload["content"] = prompt;

            // 2. 使用协议构造带event和session_id的完整请求消息
            auto message = common::Protocol::BuildFullRequest(
                common::events::CHAT_TEXT_QUERY,
                session_id_,
                payload
            );

            // 3. 通过WebSocket直接发送数据
            ws_->write(net::buffer(message));

            LOG_INFO("Sent prompt query: {}", prompt);
        } catch (const std::exception& e) {
            LOG_ERROR("Failed to send text query: {}", e.what());
            throw;
        }
    }

    common::ParsedResponse ReceiveResponse() {
        if (!connected_ || !ws_) {
            throw std::runtime_error("Not connected");
        }

        beast::flat_buffer resp_buffer;
        ws_->read(resp_buffer);

        std::vector<uint8_t> resp_data(resp_buffer.size());
        net::buffer_copy(net::buffer(resp_data), resp_buffer.data());
        return common::Protocol::ParseResponse(resp_data);
    }

        // using ResponseCallback = std::function<void(const common::ParsedResponse&)>;
    void SetResponseCallback(ResponseCallback callback) {
        bool should_start = false;
        {
            std::lock_guard<std::mutex> lock(callback_mutex_);
            callback_ = std::move(callback);
            should_start = connected_ && callback_ && !running_;
        }
        if (should_start) {
            StartReceiveThread();
        }
    }

    bool IsConnected() const {
        return connected_;
    }

    void StartReceiveThread() {
        bool has_callback = false;
        {
            std::lock_guard<std::mutex> lock(callback_mutex_);
            has_callback = static_cast<bool>(callback_);
        }
        if (!has_callback || !connected_) {
            return;
        }

        std::lock_guard<std::mutex> lock(receive_thread_mutex_);
        if (running_) {
            return;
        }
        if (receive_thread_.joinable()) {
            if (receive_thread_.get_id() == std::this_thread::get_id()) {
                return;
            }
            receive_thread_.join();
        }

        // 启动接收线程
        running_ = true;
        receive_thread_ = std::thread([this]() {
            ReceiveLoop();
        });
        LOG_INFO("Receive thread started");
    }

    void Close() {
        if (!connected_ && !running_) {
            std::lock_guard<std::mutex> lock(receive_thread_mutex_);
            if (receive_thread_.joinable()) {
                if (receive_thread_.get_id() == std::this_thread::get_id()) {
                    receive_thread_.detach();
                } else {
                    receive_thread_.join();
                }
            }
            return;
        }

        LOG_INFO("Closing connection...");

        try {
            // 1. 停止接收线程
            if (running_) {
                running_ = false;
            }
            
            // 2. 发送FINISH_SESSION请求（如果已连接）
            if (connected_ && ws_) {
                try {
                    SendFinishSession();
                    LOG_INFO("Finish session sent");
                } catch (const std::exception& e) {
                    LOG_ERROR("Failed to send finish session: {}", e.what());
                }
            }

            // 3. 发送FINISH_CONNECTION请求（如果已连接）
            if (connected_ && ws_) {
                try {
                    SendFinishConnection();
                    LOG_INFO("Finish connection sent");
                } catch (const std::exception& e) {
                    LOG_ERROR("Failed to send finish connection: {}", e.what());
                }
            }

            // 4. 关闭WebSocket（发送Close帧）
            if (ws_) {
                try {
                    // 先关闭WebSocket
                    ws_->close(websocket::close_code::normal);
                    LOG_INFO("WebSocket closed");
                } catch (const std::exception& e) {
                    LOG_ERROR("Error closing WebSocket: {}", e.what());
                }
            }

            // 5. 等待接收线程退出
            std::lock_guard<std::mutex> lock(receive_thread_mutex_);
            if (receive_thread_.joinable()) {
                try {
                    if (receive_thread_.get_id() == std::this_thread::get_id()) {
                        receive_thread_.detach();
                        LOG_INFO("Receive thread detached during self-close");
                    } else {
                        receive_thread_.join();
                        LOG_INFO("Receive thread joined");
                    }
                } catch (const std::exception& e) {
                    LOG_ERROR("Error joining receive thread: {}", e.what());
                }
            }

            // 重置状态
            connected_ = false;
            running_ = false;
            ws_.reset();

            LOG_INFO("Connection closed successfully");

        } catch (const std::exception& e) {
            LOG_ERROR("Unexpected error during close: {}", e.what());
            // 确保状态被重置
            connected_ = false;
            running_ = false;
            ws_.reset();
        } 
    }

private:
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

    void SendStartConnection() {
        try {
            // 构造空JSON作为payload，表示不带附加参数
            nlohmann::json payload = nlohmann::json::object();

            // 构造WebSocket请求，START_CONNECTION事件无需session_id，可置空
            auto message = common::Protocol::BuildFullRequest(
                common::events::START_CONNECTION,
                "",   // START_CONNECTION 默认不带session_id
                payload
            );

            LOG_INFO("SendStartConnection message: {} bytes", message.size());

            // 发送请求
            ws_->write(net::buffer(message));

            // 接收服务端响应
            beast::flat_buffer resp_buffer;
            ws_->read(resp_buffer);

            std::vector<uint8_t> resp_data(resp_buffer.size());
            net::buffer_copy(net::buffer(resp_data), resp_buffer.data());

            auto response = common::Protocol::ParseResponse(resp_data);

            LOG_INFO("StartConnection response event: {}", response.event);
        } catch (const std::exception& e) {
            LOG_ERROR("Failed to send start connection request: {}", e.what());
            throw;
        }
    }
    
    // 作用：在已连接基础上，创建一场具体面试会话
        // payload 里带会话参数（采样率、音频格式、VAD/TTS等配置）
    void SendStartSession(){
        try {
            // 生成session_id
            session_id_ = GenerateSessionId();

            // 从Config获取StartSession请求参数
            auto& config = common::Config::Instance();
            nlohmann::json payload = config.GenerateStartSessionRequest();

            // 构造WebSocket请求，START_SESSION事件携带session_id 
            auto message = common::Protocol::BuildFullRequest(common::events::START_SESSION, session_id_, payload);

            LOG_INFO("SendStartSession message: {} bytes", message.size());

            // 发送请求
            ws_->write(net::buffer(message));
            LOG_INFO("StartSession request sent, response will be handled by receive thread");

        } catch (const std::exception& e) {
            LOG_ERROR("SendStartSession error: ", e.what());
            throw;
        }
    }

    void SendFinishSession() {
        // 创建一个 空的 JSON 对象
        nlohmann::json payload = nlohmann::json::object();
        auto message = common::Protocol::BuildFullRequest(common::events::FINISH_SESSION, session_id_, payload);

        ws_->write(net::buffer(message));
    }

    void SendFinishConnection() { 
        // 作用：在会话结束后，关闭WebSocket连接
        nlohmann::json payload = nlohmann::json::object();
        auto message = common::Protocol::BuildFullRequest(common::events::FINISH_CONNECTION, "", payload);

        ws_->write(net::buffer(message));
    }

    void ReceiveLoop() {
        while (running_ && connected_) {
            try {
                auto response = ReceiveResponse();

                ResponseCallback callback_copy;
                {
                    std::lock_guard<std::mutex> lock(callback_mutex_);
                    callback_copy = callback_;
                }
                if (callback_copy) {
                    callback_copy(response);
                }

                // 检查会话结束事件
                if (response.event == common::events::SESSION_FINISHED ||
                    response.event == common::events::SESSION_ENDED) {
                    LOG_INFO("Session finished event: ", response.event);
                    connected_ = false;
                    running_ = false;
                    break;
                }

            } catch (const std::exception& e) {
                if (running_) {
                    LOG_ERROR("Receive loop error: ", e.what());
                }
                connected_ = false;
                running_ = false;
                break;
            }
        }
    }

    std::string GenerateSessionId() {
        return common::GenerateUUID();
    }
private:
    std::string url_;
    std::string host_;
    std::string port_;
    std::string path_;
    std::string session_id_;
    std::map<std::string, std::string> headers_;

    net::io_context ioc_;
    ssl::context ssl_ctx_;
    tcp::resolver resolver_;
    std::unique_ptr<websocket::stream<beast::ssl_stream<tcp::socket>>> ws_;

    std::atomic<bool> connected_;
    std::atomic<bool> running_;
    std::thread receive_thread_;
    std::mutex receive_thread_mutex_;
    std::mutex callback_mutex_;
    // callback_ 在 RealtimeClient 里
    // 就是“把服务端消息抛给上层业务”的函数指针（std::function）。
    ResponseCallback callback_;
};

RealtimeClient::RealtimeClient(const std::string& url,
                               const std::map<std::string, std::string>& headers)
    : pimpl_(std::make_unique<RealtimeClientImpl>(url, headers)) {
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

common::ParsedResponse RealtimeClient::ReceiveResponse() {
    return pimpl_->ReceiveResponse();
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
