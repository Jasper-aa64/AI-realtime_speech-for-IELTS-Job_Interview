// RealtimeClient 的连接层测试：进程内起一个假的 TLS WebSocket 服务端（只回协议需要的几个事件），
// 不连真实服务、不用麦克风。重点测并发发送不坏帧、关闭有界、网络卡住时发送不阻塞。
#include <gtest/gtest.h>

#include "services/realtime_client.h"
#include "common/logger.h"
#include "common/protocol.h"
#include "fake_realtime_server.h"

#include <nlohmann/json.hpp>


#include <algorithm>
#include <atomic>
#include <chrono>
#include <fstream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

using interview::services::RealtimeClient;
using interview::services::RealtimeClientOptions;

using namespace fake_realtime;

namespace {

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

    // 火山文档把 dialog.extra.model 标为必传
    const auto start_session = server.Frames()[1];
    const auto payload = nlohmann::json::parse(start_session.payload.begin(), start_session.payload.end());
    EXPECT_EQ(payload["dialog"]["extra"]["model"], "1.2.1.1");
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

// SendEvent 原样发出调用方给的事件号和 JSON（SayHello / ChatTTSText 用它）
TEST(RealtimeClientTest, SendEventCarriesEventAndPayload) {
    FakeServer server({});
    RealtimeClient client(Url(server.port()), {}, TestOptions());
    client.Connect();
    client.SendEvent(events::SAY_HELLO, {{"content", "你好"}});
    client.SendEvent(events::CHAT_TTS_TEXT, {{"start", true}, {"content", "第一题"}, {"end", false}});
    client.Close();
    std::vector<ClientFrame> sent;
    for (const auto& f : server.Frames()) {
        if (f.event == events::SAY_HELLO || f.event == events::CHAT_TTS_TEXT) sent.push_back(f);
    }
    ASSERT_EQ(sent.size(), 2u);
    EXPECT_EQ(sent[0].event, events::SAY_HELLO);
    EXPECT_EQ(nlohmann::json::parse(sent[0].payload.begin(), sent[0].payload.end())["content"], "你好");
    const auto tts = nlohmann::json::parse(sent[1].payload.begin(), sent[1].payload.end());
    EXPECT_EQ(tts["content"], "第一题");
    EXPECT_TRUE(tts["start"].get<bool>());
    EXPECT_FALSE(sent[1].session_id.empty());
}

// 调用方给了 StartSession payload 时用它，不读全局 Config
TEST(RealtimeClientTest, StartSessionPayloadOverride) {
    FakeServer server({});
    auto options = TestOptions();
    options.start_session = {{"dialog", {{"extra", {{"model", "2.2.0.0"}, {"input_mod", "keep_alive"}}}}}};
    RealtimeClient client(Url(server.port()), {}, options);
    client.Connect();
    const auto frame = server.Frames()[1];
    ASSERT_EQ(frame.event, events::START_SESSION);
    const auto payload = nlohmann::json::parse(frame.payload.begin(), frame.payload.end());
    EXPECT_EQ(payload["dialog"]["extra"]["model"], "2.2.0.0");
    EXPECT_EQ(payload["dialog"]["extra"]["input_mod"], "keep_alive");
    client.Close();
}

#ifdef __APPLE__
// macOS：ca_file 为空时找到系统自带的 CA 文件，不关掉校验
TEST(RealtimeClientTest, MacFindsSystemCaFile) {
    const auto path = interview::services::ResolveDefaultCaFile();
    EXPECT_FALSE(path.empty());
    EXPECT_TRUE(std::ifstream(path).good()) << path;
}
#endif
