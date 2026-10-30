// RealtimeClient / VoiceSession 测试共用的假服务端：进程内的 TLS WebSocket，按火山实时对话协议
// 回 CONNECTION_STARTED / SESSION_STARTED / SESSION_FINISHED，其余事件交给测试注册的 on_frame。
// 只被单个测试 .cpp 包含，所以放在匿名命名空间里。
#pragma once

#include "common/protocol.h"

#include <nlohmann/json.hpp>

#include <boost/asio/ip/tcp.hpp>
#include <boost/asio/ssl.hpp>
#include <boost/beast/core.hpp>
#include <boost/beast/ssl.hpp>
#include <boost/beast/websocket.hpp>
#include <boost/beast/websocket/ssl.hpp>

#include <atomic>
#include <chrono>
#include <fstream>
#include <functional>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace fake_realtime {

namespace beast = boost::beast;
namespace websocket = beast::websocket;
namespace net = boost::asio;
namespace ssl = boost::asio::ssl;
using tcp = boost::asio::ip::tcp;
namespace events = interview::common::events;

namespace {

// 只给测试用的自签名证书（CN=localhost），私钥不保护任何东西
const char kTestCert[] = R"(-----BEGIN CERTIFICATE-----
MIIBlDCCATugAwIBAgIUZgopxMAIzPRn2uLkqJRBjfcnoBYwCgYIKoZIzj0EAwIw
FDESMBAGA1UEAwwJbG9jYWxob3N0MCAXDTI2MTAzMDAzNDYwMFoYDzIxMjYxMDA2
MDM0NjAwWjAUMRIwEAYDVQQDDAlsb2NhbGhvc3QwWTATBgcqhkjOPQIBBggqhkjO
PQMBBwNCAASI+UKlI8mClisloYmUpTceecKWVVOGAYLgB3fk2mQ/+BJy33bGi2A3
5S/ng6BovUqdruk5qgZ8kOWejpxuMhWoo2kwZzAdBgNVHQ4EFgQUhpxyLmjSOwAY
sKdy278yUPR9fsUwHwYDVR0jBBgwFoAUhpxyLmjSOwAYsKdy278yUPR9fsUwDwYD
VR0TAQH/BAUwAwEB/zAUBgNVHREEDTALgglsb2NhbGhvc3QwCgYIKoZIzj0EAwID
RwAwRAIgR5gtMZpsSAVoJllbxdVt2sBNW7C2TuZTGc4j7L1qzkgCIDPu3B23CN2n
VBWgRV/IBPs+OWnWnMQe3imCyqeEQrQp
-----END CERTIFICATE-----
)";

const char kTestKey[] = R"(-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgfFkhvqz8rI22loJB
+3euDykLOXpJhO0tmgI31cIfeoKhRANCAASI+UKlI8mClisloYmUpTceecKWVVOG
AYLgB3fk2mQ/+BJy33bGi2A35S/ng6BovUqdruk5qgZ8kOWejpxuMhWo
-----END PRIVATE KEY-----
)";

using Clock = std::chrono::steady_clock;

long ElapsedMs(Clock::time_point start) {
    return static_cast<long>(std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - start).count());
}

template <typename Pred>
bool WaitFor(Pred pred, std::chrono::milliseconds limit = std::chrono::milliseconds(3000)) {
    const auto deadline = Clock::now() + limit;
    while (Clock::now() < deadline) {
        if (pred()) {
            return true;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    return pred();
}

void AppendU32(std::vector<uint8_t>& out, uint32_t v) {
    out.push_back(static_cast<uint8_t>(v >> 24));
    out.push_back(static_cast<uint8_t>(v >> 16));
    out.push_back(static_cast<uint8_t>(v >> 8));
    out.push_back(static_cast<uint8_t>(v));
}

uint32_t ReadU32(const std::vector<uint8_t>& d, size_t at) {
    return (uint32_t(d[at]) << 24) | (uint32_t(d[at + 1]) << 16) | (uint32_t(d[at + 2]) << 8) | uint32_t(d[at + 3]);
}

bool IsConnectionEvent(uint32_t e) {
    return e == events::START_CONNECTION || e == events::FINISH_CONNECTION ||
           e == events::CONNECTION_STARTED || e == events::CONNECTION_FAILED ||
           e == events::CONNECTION_FINISHED;
}

// 服务端发给客户端的完整响应帧：JSON、无压缩、带事件号
std::vector<uint8_t> ServerFrame(uint32_t event, const std::string& session_id, const std::string& json) {
    std::vector<uint8_t> f{0x11, 0x94, 0x10, 0x00};
    AppendU32(f, event);
    if (!IsConnectionEvent(event)) {
        AppendU32(f, static_cast<uint32_t>(session_id.size()));
        f.insert(f.end(), session_id.begin(), session_id.end());
    } else {
        const std::string connect_id = "c1";
        AppendU32(f, static_cast<uint32_t>(connect_id.size()));
        f.insert(f.end(), connect_id.begin(), connect_id.end());
    }
    AppendU32(f, static_cast<uint32_t>(json.size()));
    f.insert(f.end(), json.begin(), json.end());
    return f;
}

// 服务端发给客户端的 TTS 音频帧（SERVER_ACK、无序列化、带事件号），和文档里的 TTSResponse 示例同一格式
std::vector<uint8_t> ServerAudioFrame(const std::string& session_id, const std::vector<uint8_t>& audio,
                                      uint32_t event = events::TTS_RESPONSE) {
    std::vector<uint8_t> f{0x11, 0xB4, 0x00, 0x00};
    AppendU32(f, event);
    AppendU32(f, static_cast<uint32_t>(session_id.size()));
    f.insert(f.end(), session_id.begin(), session_id.end());
    AppendU32(f, static_cast<uint32_t>(audio.size()));
    f.insert(f.end(), audio.begin(), audio.end());
    return f;
}

// 服务端按协议严格解析客户端帧：长度字段必须和实际字节数刚好对上，否则算坏帧
struct ClientFrame {
    bool ok = false;
    uint32_t event = 0;
    std::string session_id;
    std::vector<uint8_t> payload;
};

ClientFrame ParseClientFrame(const std::vector<uint8_t>& d) {
    ClientFrame f;
    if (d.size() < 12 || (d[0] & 0x0F) != 1 || (d[1] & 0x04) == 0) {
        return f;
    }
    size_t at = 4;
    f.event = ReadU32(d, at);
    at += 4;
    if (!IsConnectionEvent(f.event)) {
        if (d.size() < at + 4) return f;
        const uint32_t sid_len = ReadU32(d, at);
        at += 4;
        if (d.size() < at + sid_len) return f;
        f.session_id.assign(reinterpret_cast<const char*>(d.data() + at), sid_len);
        at += sid_len;
    }
    if (d.size() < at + 4) return f;
    const uint32_t len = ReadU32(d, at);
    at += 4;
    if (d.size() != at + len) return f;
    f.payload.assign(d.begin() + static_cast<long>(at), d.end());
    f.ok = true;
    return f;
}

std::string CaFile() {
    static const std::string path = [] {
        const std::string p = "realtime_client_test_ca.pem";
        std::ofstream(p) << kTestCert;
        return p;
    }();
    return path;
}

struct ClientFrame;
// on_frame 里往客户端写帧用；和服务线程的读在同一线程，不需要加锁
using SendToClient = std::function<void(const std::vector<uint8_t>&)>;

struct ServerBehavior {
    // 连接、会话控制以外的每个客户端帧（含 TASK_REQUEST 音频）都交给它；session_id 是当前会话
    std::function<void(const ClientFrame&, const std::string& session_id, const SendToClient&)> on_frame;
    std::string session_started_json = R"({"dialog_id":"d1"})";

    int session_started_delay_ms = 0;
    bool reply_finish_session = true;          // false：收到 FINISH_SESSION 后既不回也不再读（模拟服务端卡住）
    bool stall_after_session_started = false;  // true：会话开始后不再读（客户端的写会积压）
    int end_session_after_audio = 0;           // >0：收到这么多音频帧后主动发 SESSION_FINISHED
};

class FakeServer {
public:
    explicit FakeServer(ServerBehavior behavior)
        : behavior_(behavior)
        , ctx_(ssl::context::tlsv12_server)
        , acceptor_(ioc_) {
        ctx_.use_certificate_chain(net::buffer(kTestCert, sizeof(kTestCert) - 1));
        ctx_.use_private_key(net::buffer(kTestKey, sizeof(kTestKey) - 1), ssl::context::pem);
        tcp::endpoint ep(net::ip::make_address("127.0.0.1"), 0);
        acceptor_.open(ep.protocol());
        acceptor_.set_option(net::socket_base::reuse_address(true));
        acceptor_.bind(ep);
        acceptor_.listen();
        port_ = acceptor_.local_endpoint().port();
        thread_ = std::thread([this] { Run(); });
    }

    ~FakeServer() {
        stop_ = true;
        try {  // 连一下，让阻塞在 accept 上的服务线程醒过来
            net::io_context io;
            tcp::socket s(io);
            s.connect(tcp::endpoint(net::ip::make_address("127.0.0.1"), port_));
        } catch (...) {
        }
        thread_.join();
    }

    unsigned short port() const { return port_; }

    std::vector<uint32_t> Events() {
        std::lock_guard<std::mutex> lock(mu_);
        std::vector<uint32_t> out;
        for (const auto& f : frames_) out.push_back(f.event);
        return out;
    }
    std::vector<ClientFrame> Frames() {
        std::lock_guard<std::mutex> lock(mu_);
        return frames_;
    }
    int Malformed() const { return malformed_; }
    bool SawClose() const { return saw_close_; }
    int Connections() const { return connections_; }

private:
    void Run() {
        while (!stop_) {
            tcp::socket sock(ioc_);
            beast::error_code ec;
            acceptor_.accept(sock, ec);
            if (ec || stop_) {
                break;
            }
            ServeOne(std::move(sock));
        }
    }

    void StallUntilStop() {
        while (!stop_) {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
    }

    void ServeOne(tcp::socket sock) {
        try {
            websocket::stream<beast::ssl_stream<tcp::socket>> ws(std::move(sock), ctx_);
            ws.next_layer().handshake(ssl::stream_base::server);
            ws.accept();
            ws.binary(true);
            ++connections_;
            int audio_seen = 0;
            std::string session_id;
            for (;;) {
                beast::flat_buffer buf;
                beast::error_code ec;
                ws.read(buf, ec);
                if (ec) {
                    if (ec == websocket::error::closed) {
                        saw_close_ = true;
                    }
                    return;
                }
                std::vector<uint8_t> bytes(buf.size());
                net::buffer_copy(net::buffer(bytes), buf.data());
                auto frame = ParseClientFrame(bytes);
                {
                    std::lock_guard<std::mutex> lock(mu_);
                    if (!frame.ok) {
                        ++malformed_;
                        continue;
                    }
                    frames_.push_back(frame);
                }
                switch (frame.event) {
                case events::START_CONNECTION:
                    ws.write(net::buffer(ServerFrame(events::CONNECTION_STARTED, "", "{}")));
                    break;
                case events::START_SESSION:
                    session_id = frame.session_id;
                    std::this_thread::sleep_for(std::chrono::milliseconds(behavior_.session_started_delay_ms));
                    ws.write(net::buffer(ServerFrame(events::SESSION_STARTED, session_id, behavior_.session_started_json)));
                    if (behavior_.stall_after_session_started) {
                        StallUntilStop();
                        return;
                    }
                    break;
                case events::TASK_REQUEST:
                    if (behavior_.end_session_after_audio > 0 && ++audio_seen == behavior_.end_session_after_audio) {
                        ws.write(net::buffer(ServerFrame(events::SESSION_FINISHED, session_id, "{}")));
                    }
                    break;
                case events::FINISH_SESSION:
                    if (!behavior_.reply_finish_session) {
                        StallUntilStop();
                        return;
                    }
                    ws.write(net::buffer(ServerFrame(events::SESSION_FINISHED, session_id, "{}")));
                    break;
                case events::FINISH_CONNECTION:
                    ws.write(net::buffer(ServerFrame(events::CONNECTION_FINISHED, "", "{}")));
                    break;
                default:
                    break;
                }
                if (behavior_.on_frame && frame.event != events::START_CONNECTION && frame.event != events::START_SESSION &&
                    frame.event != events::FINISH_SESSION && frame.event != events::FINISH_CONNECTION) {
                    behavior_.on_frame(frame, session_id, [&ws](const std::vector<uint8_t>& bytes) {
                        ws.write(net::buffer(bytes));
                    });
                }
            }
        } catch (const std::exception&) {
            // 客户端握手失败或提前断开：接着等下一个连接
        }
    }

    ServerBehavior behavior_;
    net::io_context ioc_;
    ssl::context ctx_;
    tcp::acceptor acceptor_;
    unsigned short port_ = 0;
    std::thread thread_;
    std::atomic<bool> stop_{false};
    std::atomic<int> malformed_{0};
    std::atomic<bool> saw_close_{false};
    std::atomic<int> connections_{0};
    std::mutex mu_;
    std::vector<ClientFrame> frames_;
};

std::string Url(unsigned short port) {
    return "wss://localhost:" + std::to_string(port) + "/api/v3/realtime/dialogue";
}

} // namespace
} // namespace fake_realtime
