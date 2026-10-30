// RealtimeClient 的连接层测试：进程内起一个假的 TLS WebSocket 服务端（只回协议需要的几个事件），
// 不连真实服务、不用麦克风。重点测并发发送不坏帧、关闭有界、网络卡住时发送不阻塞。
#include <gtest/gtest.h>

#include "services/realtime_client.h"
#include "common/logger.h"
#include "common/protocol.h"

#include <boost/asio/ip/tcp.hpp>
#include <boost/asio/ssl.hpp>
#include <boost/beast/core.hpp>
#include <boost/beast/ssl.hpp>
#include <boost/beast/websocket.hpp>
#include <boost/beast/websocket/ssl.hpp>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <fstream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace beast = boost::beast;
namespace websocket = beast::websocket;
namespace net = boost::asio;
namespace ssl = boost::asio::ssl;
using tcp = boost::asio::ip::tcp;
using interview::services::RealtimeClient;
using interview::services::RealtimeClientOptions;
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

struct ServerBehavior {
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
                    ws.write(net::buffer(ServerFrame(events::SESSION_STARTED, session_id, R"({"dialog_id":"d1"})")));
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

RealtimeClientOptions TestOptions() {
    RealtimeClientOptions o;
    o.tls_verify = true;
    o.ca_file = CaFile();
    o.connect_timeout = std::chrono::milliseconds(5000);
    o.finish_session_wait = std::chrono::milliseconds(300);
    o.close_timeout = std::chrono::milliseconds(1500);
    return o;
}

std::vector<uint8_t> Pcm(uint32_t seq, size_t bytes) {
    std::vector<uint8_t> pcm(bytes, 0);
    pcm[0] = static_cast<uint8_t>(seq >> 24);
    pcm[1] = static_cast<uint8_t>(seq >> 16);
    pcm[2] = static_cast<uint8_t>(seq >> 8);
    pcm[3] = static_cast<uint8_t>(seq);
    return pcm;
}

} // namespace

// 收到 SESSION_STARTED 才算连上；没设回调时它进收件箱
TEST(RealtimeClientTest, ConnectWaitsForSessionStarted) {
    ServerBehavior behavior;
    behavior.session_started_delay_ms = 300;
    FakeServer server(behavior);
    RealtimeClient client(Url(server.port()), {}, TestOptions());

    const auto start = Clock::now();
    client.Connect();
    EXPECT_GE(ElapsedMs(start), 250);
    EXPECT_TRUE(client.IsConnected());

    const auto ev = server.Events();
    ASSERT_GE(ev.size(), 2u);
    EXPECT_EQ(ev[0], events::START_CONNECTION);
    EXPECT_EQ(ev[1], events::START_SESSION);
    EXPECT_EQ(server.Malformed(), 0);
    EXPECT_EQ(client.ReceiveResponse().event, events::SESSION_STARTED);
}

// 证书校验开着、又不信任测试证书时，连接失败并说明是 TLS
TEST(RealtimeClientTest, TlsVerificationRejectsUntrustedCertificate) {
    FakeServer server({});
    auto options = TestOptions();
    options.ca_file.clear();
    RealtimeClient client(Url(server.port()), {}, options);
    try {
        client.Connect();
        FAIL() << "Connect should fail when the certificate is not trusted";
    } catch (const std::runtime_error& e) {
        EXPECT_NE(std::string(e.what()).find("TLS handshake"), std::string::npos) << e.what();
    }
    EXPECT_FALSE(client.IsConnected());
}

// 两个线程同时狂发：服务端收到的每一帧都完整，各自的顺序不变，一帧不丢
TEST(RealtimeClientTest, ConcurrentSendersProduceWellFormedFrames) {
    FakeServer server({});
    auto options = TestOptions();
    options.max_audio_backlog_bytes = 64u << 20;  // 这个测试不允许丢
    RealtimeClient client(Url(server.port()), {}, options);
    client.Connect();

    constexpr uint32_t kAudio = 3000;
    constexpr int kText = 300;
    std::thread audio([&] {
        for (uint32_t i = 0; i < kAudio; ++i) client.SendAudioData(Pcm(i, 640));
    });
    std::thread text([&] {
        for (int i = 0; i < kText; ++i) client.SendTextQuery("q" + std::to_string(i) + "#");
    });
    audio.join();
    text.join();
    client.Close();

    EXPECT_EQ(server.Malformed(), 0);
    std::vector<uint32_t> seqs;
    std::vector<int> queries;
    for (const auto& f : server.Frames()) {
        if (f.event == events::TASK_REQUEST) {
            seqs.push_back(ReadU32(f.payload, 0));
        } else if (f.event == events::CHAT_TEXT_QUERY) {
            const std::string body(f.payload.begin(), f.payload.end());
            const auto q = body.find("q");
            const auto hash = body.find('#', q);
            ASSERT_NE(hash, std::string::npos);
            queries.push_back(std::stoi(body.substr(q + 1, hash - q - 1)));
        }
    }
    ASSERT_EQ(seqs.size(), kAudio);
    for (uint32_t i = 0; i < kAudio; ++i) ASSERT_EQ(seqs[i], i);
    ASSERT_EQ(queries.size(), static_cast<size_t>(kText));
    for (int i = 0; i < kText; ++i) ASSERT_EQ(queries[i], i);

    const auto stats = client.GetStats();
    EXPECT_EQ(stats.audio_frames_sent, kAudio);
    EXPECT_EQ(stats.audio_frames_dropped, 0u);
}

// 正常关闭：排队的音频先发完，然后 FINISH_SESSION、FINISH_CONNECTION、close 帧，顺序固定
TEST(RealtimeClientTest, CloseSendsEndFramesInOrder) {
    FakeServer server({});
    RealtimeClient client(Url(server.port()), {}, TestOptions());
    client.Connect();
    for (uint32_t i = 0; i < 3; ++i) client.SendAudioData(Pcm(i, 640));
    client.Close();
    EXPECT_FALSE(client.IsConnected());

    ASSERT_TRUE(WaitFor([&] { return server.SawClose(); }));
    const auto ev = server.Events();
    ASSERT_EQ(ev.size(), 7u);
    EXPECT_EQ(ev[2], events::TASK_REQUEST);
    EXPECT_EQ(ev[4], events::TASK_REQUEST);
    EXPECT_EQ(ev[5], events::FINISH_SESSION);
    EXPECT_EQ(ev[6], events::FINISH_CONNECTION);
}

// 服务端收到 FINISH_SESSION 后再也不回：Close 在总时限内返回
TEST(RealtimeClientTest, CloseWithSilentServerIsBounded) {
    ServerBehavior behavior;
    behavior.reply_finish_session = false;
    FakeServer server(behavior);
    auto options = TestOptions();
    options.finish_session_wait = std::chrono::milliseconds(200);
    options.close_timeout = std::chrono::milliseconds(800);
    RealtimeClient client(Url(server.port()), {}, options);
    client.Connect();

    const auto start = Clock::now();
    client.Close();
    EXPECT_LT(ElapsedMs(start), 1800);
    EXPECT_FALSE(client.IsConnected());
}

// 服务端不读了，客户端一直发：SendAudioData 从不阻塞，积压超限后丢最旧的并计数，关闭仍有界
TEST(RealtimeClientTest, SendAudioNeverBlocksWhenServerStalls) {
    ServerBehavior behavior;
    behavior.stall_after_session_started = true;
    FakeServer server(behavior);
    auto options = TestOptions();
    options.close_timeout = std::chrono::milliseconds(800);
    RealtimeClient client(Url(server.port()), {}, options);
    client.Connect();

    const auto chunk = Pcm(0, 6400);   // 16 kHz int16 下 200 ms
    long worst_us = 0;
    for (int i = 0; i < 5000; ++i) {   // 约 32 MB，远超两端 TCP 缓冲
        const auto t = Clock::now();
        client.SendAudioData(chunk);
        worst_us = std::max<long>(worst_us, static_cast<long>(
            std::chrono::duration_cast<std::chrono::microseconds>(Clock::now() - t).count()));
    }
    EXPECT_TRUE(WaitFor([&] { return client.GetStats().audio_frames_dropped > 0; }));
    EXPECT_LT(worst_us, 50000) << "SendAudioData blocked for " << worst_us << " us";

    const auto start = Clock::now();
    client.Close();
    EXPECT_LT(ElapsedMs(start), 1800);
}

// 服务端先结束会话：回调照常收到；回调里调 Close() 不会死锁；之后不再发 FINISH_SESSION
TEST(RealtimeClientTest, ServerEndedSessionAndCloseFromCallback) {
    ServerBehavior behavior;
    behavior.end_session_after_audio = 3;
    FakeServer server(behavior);
    RealtimeClient client(Url(server.port()), {}, TestOptions());
    std::atomic<bool> finished{false};
    client.SetResponseCallback([&](const interview::common::ParsedResponse& r) {
        if (r.event == events::SESSION_FINISHED) {
            client.Close();
            finished = true;
        }
    });
    client.Connect();
    for (uint32_t i = 0; i < 3; ++i) client.SendAudioData(Pcm(i, 640));

    ASSERT_TRUE(WaitFor([&] { return finished.load(); }));
    EXPECT_FALSE(client.IsConnected());
    EXPECT_THROW(client.SendAudioData(Pcm(9, 640)), std::runtime_error);
    ASSERT_TRUE(WaitFor([&] { return server.SawClose(); }));
    const auto ev = server.Events();
    EXPECT_EQ(std::count(ev.begin(), ev.end(), events::FINISH_SESSION), 0);
    EXPECT_EQ(std::count(ev.begin(), ev.end(), events::FINISH_CONNECTION), 1);
}

// 没连接时保持原来的约定：发送和收消息抛异常，设回调、关闭不抛（两参数构造函数从 Config 取参数）
TEST(RealtimeClientTest, UnconnectedClientKeepsOldContract) {
    RealtimeClient client("wss://example.com/test", {{"X-Test-Header", "test-value"}});
    EXPECT_FALSE(client.IsConnected());
    EXPECT_THROW(client.SendAudioData(Pcm(0, 640)), std::runtime_error);
    EXPECT_THROW(client.SendTextQuery("x"), std::runtime_error);
    EXPECT_THROW(client.ReceiveResponse(), std::runtime_error);
    EXPECT_NO_THROW(client.SetResponseCallback([](const interview::common::ParsedResponse&) {}));
    EXPECT_NO_THROW(client.Close());
    EXPECT_NO_THROW(client.Close());
}

// 连不上：Connect 抛异常、状态干净，之后 Close 和析构都正常
TEST(RealtimeClientTest, ConnectFailureCleansUp) {
    unsigned short port = 0;
    {
        FakeServer server({});
        port = server.port();
    }
    RealtimeClient client(Url(port), {}, TestOptions());
    EXPECT_THROW(client.Connect(), std::runtime_error);
    EXPECT_FALSE(client.IsConnected());
    EXPECT_THROW(client.SendAudioData(Pcm(0, 640)), std::runtime_error);
    EXPECT_NO_THROW(client.Close());
}

// 同一个对象反复连接、发送、关闭
TEST(RealtimeClientTest, RapidReconnectCycles) {
    FakeServer server({});
    RealtimeClient client(Url(server.port()), {}, TestOptions());
    for (int i = 0; i < 20; ++i) {
        client.Connect();
        ASSERT_TRUE(client.IsConnected());
        client.SendAudioData(Pcm(static_cast<uint32_t>(i), 640));
        client.SendTextQuery("x");
        client.Close();
        ASSERT_FALSE(client.IsConnected());
    }
    EXPECT_TRUE(WaitFor([&] { return server.Connections() == 20; }));
    EXPECT_EQ(server.Malformed(), 0);
}

int main(int argc, char** argv) {
    interview::common::Logger::Init("realtime_client_test.log", false);
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
