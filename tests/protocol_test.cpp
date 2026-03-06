/**
 * @file protocol_test.cpp
 * @brief Protocol 类的单元测试
 * 
 * 测试覆盖：
 * 1. ParseResponse - 各种消息类型和边界条件
 * 2. BuildFullRequest - 完整请求构建
 * 3. BuildClientAudioRequest - 音频请求构建
 * 4. CompressGzip/DecompressGzip - 压缩解压
 * 5. BigEndian 读写 - 字节序转换
 */

#include <gtest/gtest.h>
#include "common/protocol.h"
#include "common/logger.h"
#include <nlohmann/json.hpp>

using namespace interview::common;

class ProtocolTest : public ::testing::Test {
protected:
    void SetUp() override {
        // 初始化日志系统（测试模式）
        Logger::Init("protocol_test.log", true);
    }

    // 辅助函数：手工构造服务端响应帧
    std::vector<uint8_t> BuildServerFrame(
        MessageType msg_type,
        MessageFlags flags,
        SerializationMethod serialization,
        CompressionType compression,
        uint8_t header_size = 1) 
    {
        std::vector<uint8_t> frame;
        // Byte 0: version(4bit) + header_size(4bit)
        frame.push_back((PROTOCOL_VERSION << 4) | header_size);
        // Byte 1: message_type(4bit) + flags(4bit)
        frame.push_back((static_cast<uint8_t>(msg_type) << 4) | static_cast<uint8_t>(flags));
        // Byte 2: serialization(4bit) + compression(4bit)
        frame.push_back((static_cast<uint8_t>(serialization) << 4) | static_cast<uint8_t>(compression));
        // Byte 3: reserved
        frame.push_back(0x00);
        return frame;
    }

    // 辅助函数：追加 uint32 大端字节序
    void AppendU32(std::vector<uint8_t>& buf, uint32_t val) {
        buf.push_back((val >> 24) & 0xFF);
        buf.push_back((val >> 16) & 0xFF);
        buf.push_back((val >> 8) & 0xFF);
        buf.push_back(val & 0xFF);
    }

    // 辅助函数：追加字符串（长度+内容）
    void AppendString(std::vector<uint8_t>& buf, const std::string& str) {
        AppendU32(buf, static_cast<uint32_t>(str.size()));
        buf.insert(buf.end(), str.begin(), str.end());
    }
};

// ==================== 测试：BigEndian 读写 ====================

TEST_F(ProtocolTest, AppendAndReadUint32BigEndian_PositiveValue) {
    // Arrange
    std::vector<uint8_t> buffer;
    uint32_t value = 0x12345678;

    // Act
    Protocol::AppendUint32BigEndian(buffer, value);

    // Assert
    ASSERT_EQ(buffer.size(), 4);
    EXPECT_EQ(buffer[0], 0x12);
    EXPECT_EQ(buffer[1], 0x34);
    EXPECT_EQ(buffer[2], 0x56);
    EXPECT_EQ(buffer[3], 0x78);
    EXPECT_EQ(Protocol::ReadUint32BigEndian(buffer.data()), value);
}

TEST_F(ProtocolTest, AppendAndReadInt32BigEndian_NegativeValue) {
    // Arrange
    std::vector<uint8_t> buffer;
    int32_t value = -12345;

    // Act
    Protocol::AppendUint32BigEndian(buffer, static_cast<uint32_t>(value));

    // Assert
    ASSERT_EQ(buffer.size(), 4);
    int32_t read_value = Protocol::ReadInt32BigEndian(buffer.data());
    EXPECT_EQ(read_value, value);
}

TEST_F(ProtocolTest, ReadUint32BigEndian_MaxValue) {
    // Arrange
    uint8_t data[] = {0xFF, 0xFF, 0xFF, 0xFF};

    // Act
    uint32_t value = Protocol::ReadUint32BigEndian(data);

    // Assert
    EXPECT_EQ(value, 0xFFFFFFFF);
}

// ==================== 测试：Gzip 压缩/解压 ====================

TEST_F(ProtocolTest, CompressAndDecompressGzip_SimpleString) {
    // Arrange
    std::string original = "Hello, World! This is a test string for GZIP compression.";
    std::vector<uint8_t> data(original.begin(), original.end());

    // Act
    auto compressed = Protocol::CompressGzip(data);
    auto decompressed = Protocol::DecompressGzip(compressed);

    // Assert
    // 小数据压缩后可能更大（GZIP header 开销），这是正常的，主要验证解压后能还原
    EXPECT_GT(compressed.size(), 0); // 压缩后至少有 GZIP 格式数据
    EXPECT_EQ(decompressed.size(), data.size());
    std::string result(decompressed.begin(), decompressed.end());
    EXPECT_EQ(result, original);
}

TEST_F(ProtocolTest, CompressAndDecompressGzip_LargeData) {
    // Arrange - 创建大量重复数据（易压缩）
    std::vector<uint8_t> data(10000, 'A');

    // Act
    auto compressed = Protocol::CompressGzip(data);
    auto decompressed = Protocol::DecompressGzip(compressed);

    // Assert
    EXPECT_LT(compressed.size(), data.size() / 10); // 压缩率应该很高
    EXPECT_EQ(decompressed, data);
}

TEST_F(ProtocolTest, CompressGzip_EmptyData) {
    // Arrange
    std::vector<uint8_t> data;

    // Act
    auto compressed = Protocol::CompressGzip(data);

    // Assert
    EXPECT_GT(compressed.size(), 0); // GZIP 头部仍然存在
}

TEST_F(ProtocolTest, DecompressGzip_EmptyData) {
    // Arrange
    std::vector<uint8_t> data;

    // Act
    auto decompressed = Protocol::DecompressGzip(data);

    // Assert
    EXPECT_EQ(decompressed.size(), 0);
}

TEST_F(ProtocolTest, DecompressGzip_InvalidData_ThrowsException) {
    // Arrange - 非法 GZIP 数据
    std::vector<uint8_t> invalid_data = {0x01, 0x02, 0x03, 0x04};

    // Act & Assert
    EXPECT_THROW(Protocol::DecompressGzip(invalid_data), std::runtime_error);
}

TEST_F(ProtocolTest, DecompressGzip_CorruptedData_ThrowsException) {
    // Arrange - 先压缩，然后破坏数据
    std::string original = "Test data for corruption";
    std::vector<uint8_t> data(original.begin(), original.end());
    auto compressed = Protocol::CompressGzip(data);
    
    // 破坏压缩数据的中间部分
    if (compressed.size() > 10) {
        compressed[compressed.size() / 2] ^= 0xFF;
    }

    // Act & Assert
    EXPECT_THROW(Protocol::DecompressGzip(compressed), std::runtime_error);
}

// ==================== 测试：ParseResponse - 边界条件 ====================

TEST_F(ProtocolTest, ParseResponse_DataTooShort_ReturnsEmpty) {
    // Arrange - 少于 4 字节
    std::vector<uint8_t> data = {0x11, 0x91};

    // Act
    auto result = Protocol::ParseResponse(data);

    // Assert
    EXPECT_TRUE(result.message_type.empty());
    EXPECT_EQ(result.event, 0);
}

TEST_F(ProtocolTest, ParseResponse_EmptyData_ReturnsEmpty) {
    // Arrange
    std::vector<uint8_t> data;

    // Act
    auto result = Protocol::ParseResponse(data);

    // Assert
    EXPECT_TRUE(result.message_type.empty());
}

TEST_F(ProtocolTest, ParseResponse_HeaderSizeTwo_PayloadStartAt8) {
    // Arrange - header_size=2，payload_start 应该是 4*2=8
    std::vector<uint8_t> data;
    data.push_back((PROTOCOL_VERSION << 4) | 0x02); // header_size=2
    data.push_back((static_cast<uint8_t>(MessageType::SERVER_FULL_RESPONSE) << 4) | 
                   static_cast<uint8_t>(MessageFlags::NO_SEQUENCE));
    data.push_back((static_cast<uint8_t>(SerializationMethod::JSON) << 4) | 
                   static_cast<uint8_t>(CompressionType::NO_COMPRESSION));
    data.push_back(0x00);
    // 填充到 8 字节（payload_start）
    data.push_back(0x00);
    data.push_back(0x00);
    data.push_back(0x00);
    data.push_back(0x00);
    // payload_size = 2
    AppendU32(data, 2);
    // payload = "{}"
    data.push_back('{');
    data.push_back('}');

    // Act
    auto result = Protocol::ParseResponse(data);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_FULL_RESPONSE");
    EXPECT_EQ(result.payload_size, 2);
}

TEST_F(ProtocolTest, ParseResponse_HeaderSizeTooLarge_ReturnsEmpty) {
    // Arrange - header_size=15，payload_start=60 超出数据范围
    std::vector<uint8_t> data;
    data.push_back((PROTOCOL_VERSION << 4) | 0x0F); // header_size=15
    data.push_back((static_cast<uint8_t>(MessageType::SERVER_FULL_RESPONSE) << 4) | 
                   static_cast<uint8_t>(MessageFlags::NO_SEQUENCE));
    data.push_back(0x00);
    data.push_back(0x00);

    // Act
    auto result = Protocol::ParseResponse(data);

    // Assert - payload_start(60) >= data.size(4)，应返回空结果
    EXPECT_TRUE(result.message_type.empty());
}

// ==================== 测试：SERVER_FULL_RESPONSE ====================

TEST_F(ProtocolTest, ParseResponse_ServerFullResponse_WithEventAndSessionId) {
    // Arrange - 构造 SERVER_FULL_RESPONSE 帧
    auto frame = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );

    // 添加 event
    AppendU32(frame, events::SESSION_FINISHED);
    
    // 添加 session_id
    std::string session_id = "test-session-123";
    AppendString(frame, session_id);

    // 添加 JSON payload
    nlohmann::json payload = {{"status", "success"}, {"message", "Session finished"}};
    std::string payload_str = payload.dump();
    AppendU32(frame, static_cast<uint32_t>(payload_str.size()));
    frame.insert(frame.end(), payload_str.begin(), payload_str.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_FULL_RESPONSE");
    EXPECT_EQ(result.event, events::SESSION_FINISHED);
    EXPECT_EQ(result.session_id, session_id);
    EXPECT_EQ(result.payload["status"], "success");
    EXPECT_EQ(result.payload["message"], "Session finished");
    EXPECT_FALSE(result.is_binary);
}

TEST_F(ProtocolTest, ParseResponse_ServerFullResponse_SkipSessionId) {
    // Arrange - CONNECTION_STARTED 事件应跳过 session_id
    auto frame = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );

    // 添加 event
    AppendU32(frame, events::CONNECTION_STARTED);
    
    // 添加 connect_id（CONNECTION_STARTED 需要 connect_id）
    std::string connect_id = "conn-456";
    AppendString(frame, connect_id);

    // 添加 JSON payload
    nlohmann::json payload = {{"connection", "established"}};
    std::string payload_str = payload.dump();
    AppendU32(frame, static_cast<uint32_t>(payload_str.size()));
    frame.insert(frame.end(), payload_str.begin(), payload_str.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_FULL_RESPONSE");
    EXPECT_EQ(result.event, events::CONNECTION_STARTED);
    EXPECT_TRUE(result.session_id.empty()); // 应跳过 session_id
    EXPECT_EQ(result.connect_id, connect_id);
    EXPECT_EQ(result.payload["connection"], "established");
}

TEST_F(ProtocolTest, ParseResponse_ServerFullResponse_NoEvent) {
    // Arrange - 不包含 event 的响应
    auto frame = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::NO_SEQUENCE,
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );

    // 添加 JSON payload
    nlohmann::json payload = {{"data", "test"}};
    std::string payload_str = payload.dump();
    AppendU32(frame, static_cast<uint32_t>(payload_str.size()));
    frame.insert(frame.end(), payload_str.begin(), payload_str.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_FULL_RESPONSE");
    EXPECT_EQ(result.event, 0); // 没有 event
    EXPECT_EQ(result.payload["data"], "test");
}

// ==================== 测试：SERVER_ACK ====================

TEST_F(ProtocolTest, ParseResponse_ServerAck_WithSequenceAndBinaryPayload) {
    // Arrange - SERVER_ACK 包含序列号和二进制音频数据
    auto frame = BuildServerFrame(
        MessageType::SERVER_ACK,
        static_cast<MessageFlags>(
            static_cast<uint8_t>(MessageFlags::POS_SEQUENCE) | 
            static_cast<uint8_t>(MessageFlags::MSG_WITH_EVENT)
        ),
        SerializationMethod::NO_SERIALIZATION,
        CompressionType::NO_COMPRESSION
    );

    // 添加 sequence (正数)
    int32_t sequence = 42;
    AppendU32(frame, static_cast<uint32_t>(sequence));

    // 添加 event
    AppendU32(frame, events::TTS_START);
    
    // 添加 session_id
    std::string session_id = "session-789";
    AppendString(frame, session_id);

    // 添加二进制音频数据
    std::vector<uint8_t> audio_data = {0x01, 0x02, 0x03, 0x04, 0x05};
    AppendU32(frame, static_cast<uint32_t>(audio_data.size()));
    frame.insert(frame.end(), audio_data.begin(), audio_data.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_ACK");
    EXPECT_EQ(result.sequence, sequence);
    EXPECT_EQ(result.event, events::TTS_START);
    EXPECT_EQ(result.session_id, session_id);
    EXPECT_TRUE(result.is_binary);
    EXPECT_EQ(result.payload_bytes, audio_data);
}

TEST_F(ProtocolTest, ParseResponse_ServerAck_NegativeSequence) {
    // Arrange - 负序列号
    auto frame = BuildServerFrame(
        MessageType::SERVER_ACK,
        static_cast<MessageFlags>(
            static_cast<uint8_t>(MessageFlags::NEG_SEQUENCE) | 
            static_cast<uint8_t>(MessageFlags::MSG_WITH_EVENT)
        ),
        SerializationMethod::NO_SERIALIZATION,
        CompressionType::NO_COMPRESSION
    );

    // 添加 sequence (负数)
    int32_t sequence = -100;
    AppendU32(frame, static_cast<uint32_t>(sequence));

    // 添加 event
    AppendU32(frame, events::ASR_RESULT);
    
    // 添加 session_id
    std::string session_id = "session-neg";
    AppendString(frame, session_id);

    // 添加空 payload
    AppendU32(frame, 0);

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_ACK");
    EXPECT_EQ(result.sequence, sequence);
    EXPECT_EQ(result.event, events::ASR_RESULT);
}

TEST_F(ProtocolTest, ParseResponse_ServerAck_JsonPayload) {
    // Arrange - SERVER_ACK 也可以包含 JSON payload
    auto frame = BuildServerFrame(
        MessageType::SERVER_ACK,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );

    // 添加 event
    AppendU32(frame, events::USER_START_SPEAKING);
    
    // 添加 session_id
    std::string session_id = "session-json";
    AppendString(frame, session_id);

    // 添加 JSON payload
    nlohmann::json payload = {{"vad_detected", true}, {"timestamp", 123456}};
    std::string payload_str = payload.dump();
    AppendU32(frame, static_cast<uint32_t>(payload_str.size()));
    frame.insert(frame.end(), payload_str.begin(), payload_str.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_ACK");
    EXPECT_EQ(result.event, events::USER_START_SPEAKING);
    EXPECT_EQ(result.session_id, session_id);
    EXPECT_FALSE(result.is_binary);
    EXPECT_EQ(result.payload["vad_detected"], true);
    EXPECT_EQ(result.payload["timestamp"], 123456);
}

// ==================== 测试：SERVER_ERROR_RESPONSE ====================

TEST_F(ProtocolTest, ParseResponse_ServerError_NoCompression) {
    // Arrange - 构造错误响应
    auto frame = BuildServerFrame(
        MessageType::SERVER_ERROR_RESPONSE,
        MessageFlags::NO_SEQUENCE,
        SerializationMethod::NO_SERIALIZATION,
        CompressionType::NO_COMPRESSION
    );

    // 添加 error_code
    uint32_t error_code = 400;
    AppendU32(frame, error_code);

    // 添加错误消息
    std::string error_msg = "Invalid request format";
    AppendU32(frame, static_cast<uint32_t>(error_msg.size()));
    frame.insert(frame.end(), error_msg.begin(), error_msg.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_ERROR");
    EXPECT_EQ(result.code, error_code);
    EXPECT_EQ(result.payload["error"], error_msg);
}

TEST_F(ProtocolTest, ParseResponse_ServerError_WithGzipCompression) {
    // Arrange - 错误消息使用 GZIP 压缩
    auto frame = BuildServerFrame(
        MessageType::SERVER_ERROR_RESPONSE,
        MessageFlags::NO_SEQUENCE,
        SerializationMethod::NO_SERIALIZATION,
        CompressionType::GZIP
    );

    // 添加 error_code
    uint32_t error_code = 500;
    AppendU32(frame, error_code);

    // 压缩错误消息
    std::string error_msg = "Internal server error occurred during processing";
    std::vector<uint8_t> error_bytes(error_msg.begin(), error_msg.end());
    auto compressed = Protocol::CompressGzip(error_bytes);

    // 添加压缩后的错误消息
    AppendU32(frame, static_cast<uint32_t>(compressed.size()));
    frame.insert(frame.end(), compressed.begin(), compressed.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_ERROR");
    EXPECT_EQ(result.code, error_code);
    EXPECT_EQ(result.payload["error"], error_msg);
}

TEST_F(ProtocolTest, ParseResponse_ServerError_InsufficientDataForErrorCode) {
    // Arrange - 数据不足以读取 error_code
    auto frame = BuildServerFrame(
        MessageType::SERVER_ERROR_RESPONSE,
        MessageFlags::NO_SEQUENCE,
        SerializationMethod::NO_SERIALIZATION,
        CompressionType::NO_COMPRESSION
    );
    // 只有 header，没有 error_code

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_TRUE(result.message_type.empty());
}

TEST_F(ProtocolTest, ParseResponse_ServerError_InsufficientDataForPayload) {
    // Arrange - 有 error_code 但 payload 数据不完整
    auto frame = BuildServerFrame(
        MessageType::SERVER_ERROR_RESPONSE,
        MessageFlags::NO_SEQUENCE,
        SerializationMethod::NO_SERIALIZATION,
        CompressionType::NO_COMPRESSION
    );

    // 添加 error_code
    AppendU32(frame, 404);

    // 声明 payload_size=100 但实际只提供 5 字节
    AppendU32(frame, 100);
    frame.insert(frame.end(), {0x01, 0x02, 0x03, 0x04, 0x05});

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert - 应检测到数据不足
    EXPECT_TRUE(result.message_type.empty());
}

// ==================== 测试：JSON 解析失败 fallback ====================

TEST_F(ProtocolTest, ParseResponse_JsonParseFailed_FallbackToBinary) {
    // Arrange - serialization=JSON 但 payload 不是合法 JSON
    auto frame = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );

    // 添加 event
    AppendU32(frame, events::TTS_END);
    
    // 添加 session_id
    std::string session_id = "session-invalid-json";
    AppendString(frame, session_id);

    // 添加非法 JSON payload
    std::string invalid_json = "This is not valid JSON {{{";
    AppendU32(frame, static_cast<uint32_t>(invalid_json.size()));
    frame.insert(frame.end(), invalid_json.begin(), invalid_json.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert - 应 fallback 到 binary
    EXPECT_EQ(result.message_type, "SERVER_FULL_RESPONSE");
    EXPECT_EQ(result.event, events::TTS_END);
    EXPECT_TRUE(result.is_binary);
    EXPECT_EQ(result.payload_bytes.size(), invalid_json.size());
    std::string recovered(result.payload_bytes.begin(), result.payload_bytes.end());
    EXPECT_EQ(recovered, invalid_json);
}

// ==================== 测试：GZIP 压缩的响应 ====================

TEST_F(ProtocolTest, ParseResponse_ServerFullResponse_WithGzipCompression) {
    // Arrange - 使用 GZIP 压缩的 JSON payload
    auto frame = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::GZIP
    );

    // 添加 event
    AppendU32(frame, events::ASR_RESULT);
    
    // 添加 session_id
    std::string session_id = "session-gzip";
    AppendString(frame, session_id);

    // 压缩 JSON payload
    nlohmann::json payload = {
        {"text", "这是一段很长的语音识别结果文本，用于测试 GZIP 压缩功能"},
        {"is_final", true},
        {"confidence", 0.95}
    };
    std::string payload_str = payload.dump();
    std::vector<uint8_t> payload_bytes(payload_str.begin(), payload_str.end());
    auto compressed = Protocol::CompressGzip(payload_bytes);

    // 添加压缩后的 payload
    AppendU32(frame, static_cast<uint32_t>(compressed.size()));
    frame.insert(frame.end(), compressed.begin(), compressed.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_FULL_RESPONSE");
    EXPECT_EQ(result.event, events::ASR_RESULT);
    EXPECT_EQ(result.session_id, session_id);
    EXPECT_FALSE(result.is_binary);
    EXPECT_EQ(result.payload["text"], payload["text"]);
    EXPECT_EQ(result.payload["is_final"], true);
}

TEST_F(ProtocolTest, ParseResponse_GzipDecompressionFailed_ReturnsEmpty) {
    // Arrange - 声明使用 GZIP 但提供非法压缩数据
    auto frame = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::GZIP
    );

    // 添加 event
    AppendU32(frame, events::SESSION_FINISHED);
    
    // 添加 session_id
    std::string session_id = "session-bad-gzip";
    AppendString(frame, session_id);

    // 添加非法 GZIP 数据
    std::vector<uint8_t> bad_gzip = {0xFF, 0xFE, 0xFD, 0xFC};
    AppendU32(frame, static_cast<uint32_t>(bad_gzip.size()));
    frame.insert(frame.end(), bad_gzip.begin(), bad_gzip.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert - 解压失败应返回空结果
    EXPECT_TRUE(result.message_type.empty());
}

// ==================== 测试：序列号解析 ====================

TEST_F(ProtocolTest, ParseResponse_InsufficientDataForSequence) {
    // Arrange - flags 包含 sequence 但数据不足
    auto frame = BuildServerFrame(
        MessageType::SERVER_ACK,
        static_cast<MessageFlags>(
            static_cast<uint8_t>(MessageFlags::POS_SEQUENCE) | 
            static_cast<uint8_t>(MessageFlags::MSG_WITH_EVENT)
        ),
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );
    // 只有 header，没有 sequence 数据

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_TRUE(result.message_type.empty());
}

TEST_F(ProtocolTest, ParseResponse_InsufficientDataForEvent) {
    // Arrange - flags 包含 event 但数据不足
    auto frame = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );
    // 只有 header，没有 event 数据

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_TRUE(result.message_type.empty());
}

TEST_F(ProtocolTest, ParseResponse_InsufficientDataForSessionId) {
    // Arrange - 有 event 但 session_id 数据不足
    auto frame = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );

    // 添加 event
    AppendU32(frame, events::SESSION_FINISHED);
    
    // 声明 session_id 长度为 100 但不提供数据
    AppendU32(frame, 100);

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_TRUE(result.message_type.empty());
}

TEST_F(ProtocolTest, ParseResponse_InsufficientDataForPayloadSize) {
    // Arrange - 有 session_id 但没有 payload_size
    auto frame = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );

    // 添加 event
    AppendU32(frame, events::SESSION_FINISHED);
    
    // 添加 session_id
    AppendString(frame, "test");
    // 缺少 payload_size

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_TRUE(result.message_type.empty());
}

// ==================== 测试：connect_id 解析 ====================

TEST_F(ProtocolTest, ParseResponse_ConnectionStarted_WithConnectId) {
    // Arrange - CONNECTION_STARTED 包含 connect_id
    auto frame = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );

    // 添加 event
    AppendU32(frame, events::CONNECTION_STARTED);
    
    // 添加 connect_id（跳过 session_id）
    std::string connect_id = "connect-abc-123";
    AppendString(frame, connect_id);

    // 添加 JSON payload
    nlohmann::json payload = {{"status", "connected"}};
    std::string payload_str = payload.dump();
    AppendU32(frame, static_cast<uint32_t>(payload_str.size()));
    frame.insert(frame.end(), payload_str.begin(), payload_str.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_FULL_RESPONSE");
    EXPECT_EQ(result.event, events::CONNECTION_STARTED);
    EXPECT_TRUE(result.session_id.empty());
    EXPECT_EQ(result.connect_id, connect_id);
}

TEST_F(ProtocolTest, ParseResponse_ConnectionFailed_WithConnectId) {
    // Arrange - CONNECTION_FAILED 包含 connect_id
    auto frame = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );

    // 添加 event
    AppendU32(frame, events::CONNECTION_FAILED);
    
    // 添加 connect_id
    std::string connect_id = "connect-failed-456";
    AppendString(frame, connect_id);

    // 添加 JSON payload
    nlohmann::json payload = {{"reason", "timeout"}};
    std::string payload_str = payload.dump();
    AppendU32(frame, static_cast<uint32_t>(payload_str.size()));
    frame.insert(frame.end(), payload_str.begin(), payload_str.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.event, events::CONNECTION_FAILED);
    EXPECT_EQ(result.connect_id, connect_id);
}

// ==================== 测试：BuildFullRequest ====================

TEST_F(ProtocolTest, BuildFullRequest_StartSession_WithSessionId) {
    // Arrange
    uint32_t event = events::START_SESSION;
    std::string session_id = "my-session-id";
    nlohmann::json payload = {
        {"app_id", "test-app"},
        {"user_id", "user-123"}
    };

    // Act
    auto request = Protocol::BuildFullRequest(event, session_id, payload);

    // Assert - 验证结构
    ASSERT_GE(request.size(), 4); // 至少有 header

    // 验证 header
    EXPECT_EQ(request[0] >> 4, PROTOCOL_VERSION);
    EXPECT_EQ(request[0] & 0x0F, DEFAULT_HEADER_SIZE);
    EXPECT_EQ(request[1] >> 4, static_cast<uint8_t>(MessageType::CLIENT_FULL_REQUEST));
    EXPECT_EQ(request[1] & 0x0F, static_cast<uint8_t>(MessageFlags::MSG_WITH_EVENT));
    EXPECT_EQ(request[2] >> 4, static_cast<uint8_t>(SerializationMethod::JSON));
    EXPECT_EQ(request[2] & 0x0F, static_cast<uint8_t>(CompressionType::NO_COMPRESSION));

    // 验证 event
    uint32_t parsed_event = Protocol::ReadUint32BigEndian(request.data() + 4);
    EXPECT_EQ(parsed_event, event);

    // 验证 session_id
    uint32_t session_id_len = Protocol::ReadUint32BigEndian(request.data() + 8);
    EXPECT_EQ(session_id_len, session_id.size());
    std::string parsed_session_id(request.begin() + 12, request.begin() + 12 + session_id_len);
    EXPECT_EQ(parsed_session_id, session_id);
}

TEST_F(ProtocolTest, BuildFullRequest_StartConnection_SkipSessionId) {
    // Arrange - START_CONNECTION 不应包含 session_id
    uint32_t event = events::START_CONNECTION;
    std::string session_id = "should-be-ignored";
    nlohmann::json payload = {{"version", "1.0"}};

    // Act
    auto request = Protocol::BuildFullRequest(event, session_id, payload);

    // Assert
    ASSERT_GE(request.size(), 4);

    // 验证 event
    uint32_t parsed_event = Protocol::ReadUint32BigEndian(request.data() + 4);
    EXPECT_EQ(parsed_event, event);

    // 验证没有 session_id，直接是 payload_size
    uint32_t payload_size = Protocol::ReadUint32BigEndian(request.data() + 8);
    std::string payload_str = payload.dump();
    EXPECT_EQ(payload_size, payload_str.size());
}

TEST_F(ProtocolTest, BuildFullRequest_EmptyPayload) {
    // Arrange
    uint32_t event = events::FINISH_SESSION;
    std::string session_id = "session-empty";
    nlohmann::json payload = nlohmann::json::object();

    // Act
    auto request = Protocol::BuildFullRequest(event, session_id, payload);

    // Assert
    ASSERT_GE(request.size(), 4);
    
    // 找到 payload_size 位置（header + event + session_id_len + session_id）
    size_t offset = 4 + 4 + 4 + session_id.size();
    uint32_t payload_size = Protocol::ReadUint32BigEndian(request.data() + offset);
    EXPECT_EQ(payload_size, 2); // "{}" = 2 bytes
}

// ==================== 测试：BuildClientAudioRequest ====================

TEST_F(ProtocolTest, BuildClientAudioRequest_WithSessionId) {
    // Arrange
    uint32_t event = events::TASK_REQUEST;
    std::string session_id = "audio-session-123";
    std::vector<uint8_t> audio_data = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05};

    // Act
    auto request = Protocol::BuildClientAudioRequest(event, session_id, audio_data);

    // Assert
    ASSERT_GE(request.size(), 4);

    // 验证 header
    EXPECT_EQ(request[1] >> 4, static_cast<uint8_t>(MessageType::CLIENT_AUDIO_ONLY_REQUEST));
    EXPECT_EQ(request[2] >> 4, static_cast<uint8_t>(SerializationMethod::NO_SERIALIZATION));

    // 验证 event
    uint32_t parsed_event = Protocol::ReadUint32BigEndian(request.data() + 4);
    EXPECT_EQ(parsed_event, event);

    // 验证 session_id
    uint32_t session_id_len = Protocol::ReadUint32BigEndian(request.data() + 8);
    EXPECT_EQ(session_id_len, session_id.size());

    // 验证 audio_data
    size_t audio_offset = 4 + 4 + 4 + session_id.size();
    uint32_t audio_size = Protocol::ReadUint32BigEndian(request.data() + audio_offset);
    EXPECT_EQ(audio_size, audio_data.size());
    
    std::vector<uint8_t> parsed_audio(
        request.begin() + audio_offset + 4,
        request.begin() + audio_offset + 4 + audio_size
    );
    EXPECT_EQ(parsed_audio, audio_data);
}

TEST_F(ProtocolTest, BuildClientAudioRequest_EmptyAudio) {
    // Arrange
    uint32_t event = events::TASK_REQUEST;
    std::string session_id = "audio-session-empty";
    std::vector<uint8_t> audio_data;

    // Act
    auto request = Protocol::BuildClientAudioRequest(event, session_id, audio_data);

    // Assert
    ASSERT_GE(request.size(), 4);
    
    // 验证 audio_size = 0
    size_t audio_offset = 4 + 4 + 4 + session_id.size();
    uint32_t audio_size = Protocol::ReadUint32BigEndian(request.data() + audio_offset);
    EXPECT_EQ(audio_size, 0);
}

TEST_F(ProtocolTest, BuildClientAudioRequest_LargeAudio) {
    // Arrange - 大音频数据（10KB）
    uint32_t event = events::TASK_REQUEST;
    std::string session_id = "audio-large";
    std::vector<uint8_t> audio_data(10240, 0xAB); // 10KB

    // Act
    auto request = Protocol::BuildClientAudioRequest(event, session_id, audio_data);

    // Assert
    size_t expected_size = 4 + 4 + 4 + session_id.size() + 4 + audio_data.size();
    EXPECT_EQ(request.size(), expected_size);
}

// ==================== 测试：不支持的消息类型 ====================

TEST_F(ProtocolTest, ParseResponse_UnsupportedMessageType_ReturnsEmpty) {
    // Arrange - 使用未定义的消息类型
    std::vector<uint8_t> frame;
    frame.push_back((PROTOCOL_VERSION << 4) | DEFAULT_HEADER_SIZE);
    frame.push_back((0b0101 << 4) | 0x00); // 未定义的消息类型 0b0101
    frame.push_back(0x00);
    frame.push_back(0x00);

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_TRUE(result.message_type.empty());
}

// ==================== 测试：不支持的序列化方法 ====================

TEST_F(ProtocolTest, ParseResponse_UnsupportedSerialization_ReturnsEmpty) {
    // Arrange - 使用 THRIFT 序列化（未实现）
    auto frame = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::THRIFT, // 未实现
        CompressionType::NO_COMPRESSION
    );

    // 添加 event
    AppendU32(frame, events::SESSION_FINISHED);
    
    // 添加 session_id
    AppendString(frame, "test");

    // 添加 payload
    std::vector<uint8_t> payload = {0x01, 0x02, 0x03};
    AppendU32(frame, static_cast<uint32_t>(payload.size()));
    frame.insert(frame.end(), payload.begin(), payload.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert - 不支持的序列化方法应返回空或错误
    EXPECT_TRUE(result.message_type.empty());
}

// ==================== 测试：复杂场景 ====================

TEST_F(ProtocolTest, ParseResponse_CompleteWorkflow_SessionLifecycle) {
    // Arrange - 模拟完整会话生命周期的响应

    // 1. CONNECTION_STARTED
    auto frame1 = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );
    AppendU32(frame1, events::CONNECTION_STARTED);
    AppendString(frame1, "conn-001");
    std::string payload1_str = R"({"status":"connected"})";
    AppendU32(frame1, static_cast<uint32_t>(payload1_str.size()));
    frame1.insert(frame1.end(), payload1_str.begin(), payload1_str.end());

    auto result1 = Protocol::ParseResponse(frame1);
    EXPECT_EQ(result1.event, events::CONNECTION_STARTED);
    EXPECT_EQ(result1.connect_id, "conn-001");

    // 2. SESSION_FINISHED
    auto frame2 = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );
    AppendU32(frame2, events::SESSION_FINISHED);
    AppendString(frame2, "session-001");
    std::string payload2_str = R"({"duration":120})";
    AppendU32(frame2, static_cast<uint32_t>(payload2_str.size()));
    frame2.insert(frame2.end(), payload2_str.begin(), payload2_str.end());

    auto result2 = Protocol::ParseResponse(frame2);
    EXPECT_EQ(result2.event, events::SESSION_FINISHED);
    EXPECT_EQ(result2.session_id, "session-001");
}

TEST_F(ProtocolTest, BuildFullRequest_ChatTextQuery_ComplexPayload) {
    // Arrange - 复杂的文本查询 payload
    uint32_t event = events::CHAT_TEXT_QUERY;
    std::string session_id = "chat-session-456";
    nlohmann::json payload = {
        {"text", "请帮我查询天气"},
        {"language", "zh-CN"},
        {"metadata", {
            {"user_id", "user-789"},
            {"timestamp", 1234567890}
        }}
    };

    // Act
    auto request = Protocol::BuildFullRequest(event, session_id, payload);

    // Assert
    ASSERT_GE(request.size(), 4);
    
    // 验证可以正确解析（模拟服务端视角）
    uint32_t parsed_event = Protocol::ReadUint32BigEndian(request.data() + 4);
    EXPECT_EQ(parsed_event, event);
}

TEST_F(ProtocolTest, RoundTrip_BuildAndParse_FullRequest) {
    // Arrange - 构建请求后模拟服务端解析
    uint32_t event = events::START_SESSION;
    std::string session_id = "roundtrip-session";
    nlohmann::json payload = {{"test", "data"}};

    // Act - 构建客户端请求
    auto request = Protocol::BuildFullRequest(event, session_id, payload);

    // 模拟服务端返回相同结构的响应（仅改变 message_type）
    auto response = request;
    response[1] = (static_cast<uint8_t>(MessageType::SERVER_FULL_RESPONSE) << 4) | 
                  (response[1] & 0x0F);

    // 解析响应
    auto parsed = Protocol::ParseResponse(response);

    // Assert
    EXPECT_EQ(parsed.message_type, "SERVER_FULL_RESPONSE");
    EXPECT_EQ(parsed.event, event);
    EXPECT_EQ(parsed.session_id, session_id);
    EXPECT_EQ(parsed.payload["test"], "data");
}

// ==================== 测试：边界情况 ====================

TEST_F(ProtocolTest, ParseResponse_PayloadSizeZero) {
    // Arrange - payload_size = 0
    auto frame = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );

    AppendU32(frame, events::SESSION_FINISHED);
    AppendString(frame, "session-zero");
    AppendU32(frame, 0); // payload_size = 0

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_FULL_RESPONSE");
    EXPECT_EQ(result.payload_size, 0);
}

TEST_F(ProtocolTest, ParseResponse_SessionIdEmpty) {
    // Arrange - session_id 长度为 0
    auto frame = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );

    AppendU32(frame, events::SESSION_FINISHED);
    AppendU32(frame, 0); // session_id 长度 = 0
    
    // 添加 payload
    std::string payload_str = R"({"ok":true})";
    AppendU32(frame, static_cast<uint32_t>(payload_str.size()));
    frame.insert(frame.end(), payload_str.begin(), payload_str.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_FULL_RESPONSE");
    EXPECT_TRUE(result.session_id.empty());
    EXPECT_EQ(result.payload["ok"], true);
}

TEST_F(ProtocolTest, BuildFullRequest_SessionIdEmpty) {
    // Arrange
    uint32_t event = events::START_SESSION;
    std::string session_id = ""; // 空 session_id
    nlohmann::json payload = {{"test", true}};

    // Act
    auto request = Protocol::BuildFullRequest(event, session_id, payload);

    // Assert
    ASSERT_GE(request.size(), 4);
    
    // 验证 session_id 长度为 0
    uint32_t session_id_len = Protocol::ReadUint32BigEndian(request.data() + 8);
    EXPECT_EQ(session_id_len, 0);
}

// ==================== 测试：所有跳过 session_id 的事件 ====================

TEST_F(ProtocolTest, ParseResponse_AllSkipSessionIdEvents) {
    // Arrange - 测试所有应跳过 session_id 的事件
    std::vector<uint32_t> skip_events = {
        events::START_CONNECTION,
        events::FINISH_CONNECTION,
        events::CONNECTION_STARTED,
        events::CONNECTION_FAILED,
        events::CONNECTION_FINISHED
    };

    for (uint32_t event : skip_events) {
        auto frame = BuildServerFrame(
            MessageType::SERVER_FULL_RESPONSE,
            MessageFlags::MSG_WITH_EVENT,
            SerializationMethod::JSON,
            CompressionType::NO_COMPRESSION
        );

        AppendU32(frame, event);
        
        // 对于连接事件，需要 connect_id
        bool needs_connect_id = (event == events::CONNECTION_STARTED ||
                                 event == events::CONNECTION_FAILED ||
                                 event == events::CONNECTION_FINISHED);
        
        if (needs_connect_id) {
            AppendString(frame, "test-connect-id");
        }

        // 添加 payload
        std::string payload_str = R"({"test":true})";
        AppendU32(frame, static_cast<uint32_t>(payload_str.size()));
        frame.insert(frame.end(), payload_str.begin(), payload_str.end());

        // Act
        auto result = Protocol::ParseResponse(frame);

        // Assert
        EXPECT_EQ(result.event, event) << "Failed for event " << event;
        EXPECT_TRUE(result.session_id.empty()) << "session_id should be empty for event " << event;
        
        if (needs_connect_id) {
            EXPECT_FALSE(result.connect_id.empty()) << "connect_id should exist for event " << event;
        }
    }
}

// ==================== 测试：所有需要 connect_id 的事件 ====================

TEST_F(ProtocolTest, ParseResponse_AllConnectIdEvents) {
    // Arrange - 测试所有需要 connect_id 的事件
    std::vector<uint32_t> connect_events = {
        events::CONNECTION_STARTED,
        events::CONNECTION_FAILED,
        events::CONNECTION_FINISHED
    };

    for (uint32_t event : connect_events) {
        auto frame = BuildServerFrame(
            MessageType::SERVER_FULL_RESPONSE,
            MessageFlags::MSG_WITH_EVENT,
            SerializationMethod::JSON,
            CompressionType::NO_COMPRESSION
        );

        AppendU32(frame, event);
        
        std::string connect_id = "connect-" + std::to_string(event);
        AppendString(frame, connect_id);

        std::string payload_str = R"({"status":"ok"})";
        AppendU32(frame, static_cast<uint32_t>(payload_str.size()));
        frame.insert(frame.end(), payload_str.begin(), payload_str.end());

        // Act
        auto result = Protocol::ParseResponse(frame);

        // Assert
        EXPECT_EQ(result.event, event) << "Failed for event " << event;
        EXPECT_EQ(result.connect_id, connect_id) << "connect_id mismatch for event " << event;
    }
}

// ==================== 测试：GenerateHeader ====================

TEST_F(ProtocolTest, GenerateHeader_DefaultParameters) {
    // Act
    auto header = Protocol::GenerateHeader();

    // Assert
    ASSERT_EQ(header.size(), 4);
    EXPECT_EQ(header[0] >> 4, PROTOCOL_VERSION);
    EXPECT_EQ(header[0] & 0x0F, DEFAULT_HEADER_SIZE);
    EXPECT_EQ(header[1] >> 4, static_cast<uint8_t>(MessageType::CLIENT_FULL_REQUEST));
    EXPECT_EQ(header[1] & 0x0F, static_cast<uint8_t>(MessageFlags::MSG_WITH_EVENT));
    EXPECT_EQ(header[2] >> 4, static_cast<uint8_t>(SerializationMethod::JSON));
    EXPECT_EQ(header[2] & 0x0F, static_cast<uint8_t>(CompressionType::NO_COMPRESSION));
    EXPECT_EQ(header[3], 0x00);
}

TEST_F(ProtocolTest, GenerateHeader_CustomParameters) {
    // Act
    auto header = Protocol::GenerateHeader(
        MessageType::CLIENT_AUDIO_ONLY_REQUEST,
        MessageFlags::POS_SEQUENCE,
        SerializationMethod::NO_SERIALIZATION,
        CompressionType::GZIP,
        0xAB
    );

    // Assert
    ASSERT_EQ(header.size(), 4);
    EXPECT_EQ(header[1] >> 4, static_cast<uint8_t>(MessageType::CLIENT_AUDIO_ONLY_REQUEST));
    EXPECT_EQ(header[1] & 0x0F, static_cast<uint8_t>(MessageFlags::POS_SEQUENCE));
    EXPECT_EQ(header[2] >> 4, static_cast<uint8_t>(SerializationMethod::NO_SERIALIZATION));
    EXPECT_EQ(header[2] & 0x0F, static_cast<uint8_t>(CompressionType::GZIP));
    EXPECT_EQ(header[3], 0xAB);
}

// ==================== 测试：组合 flags ====================

TEST_F(ProtocolTest, ParseResponse_CombinedFlags_SequenceAndEvent) {
    // Arrange - 同时包含 POS_SEQUENCE 和 MSG_WITH_EVENT
    auto frame = BuildServerFrame(
        MessageType::SERVER_ACK,
        static_cast<MessageFlags>(
            static_cast<uint8_t>(MessageFlags::POS_SEQUENCE) | 
            static_cast<uint8_t>(MessageFlags::MSG_WITH_EVENT)
        ),
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );

    // 添加 sequence
    AppendU32(frame, 999);

    // 添加 event
    AppendU32(frame, events::ASR_RESULT);
    
    // 添加 session_id
    AppendString(frame, "combined-session");

    // 添加 payload
    nlohmann::json payload = {{"text", "测试"}};
    std::string payload_str = payload.dump();
    AppendU32(frame, static_cast<uint32_t>(payload_str.size()));
    frame.insert(frame.end(), payload_str.begin(), payload_str.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_ACK");
    EXPECT_EQ(result.sequence, 999);
    EXPECT_EQ(result.event, events::ASR_RESULT);
    EXPECT_EQ(result.session_id, "combined-session");
    EXPECT_EQ(result.payload["text"], "测试");
}

// ==================== 测试：压缩 + JSON 组合 ====================

TEST_F(ProtocolTest, ParseResponse_GzipAndJson_ServerAck) {
    // Arrange - SERVER_ACK 使用 GZIP + JSON
    auto frame = BuildServerFrame(
        MessageType::SERVER_ACK,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::GZIP
    );

    AppendU32(frame, events::TTS_END);
    AppendString(frame, "gzip-json-session");

    // 压缩 JSON payload
    nlohmann::json payload = {
        {"audio_duration", 5.5},
        {"samples", 88000},
        {"format", "pcm_16khz"}
    };
    std::string payload_str = payload.dump();
    std::vector<uint8_t> payload_bytes(payload_str.begin(), payload_str.end());
    auto compressed = Protocol::CompressGzip(payload_bytes);

    AppendU32(frame, static_cast<uint32_t>(compressed.size()));
    frame.insert(frame.end(), compressed.begin(), compressed.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_ACK");
    EXPECT_EQ(result.event, events::TTS_END);
    EXPECT_FALSE(result.is_binary);
    EXPECT_EQ(result.payload["audio_duration"], 5.5);
    EXPECT_EQ(result.payload["samples"], 88000);
}

// ==================== 测试：错误响应的 GZIP 解压失败 ====================

TEST_F(ProtocolTest, ParseResponse_ServerError_GzipDecompressionFailed) {
    // Arrange - 错误响应声明 GZIP 但数据非法
    auto frame = BuildServerFrame(
        MessageType::SERVER_ERROR_RESPONSE,
        MessageFlags::NO_SEQUENCE,
        SerializationMethod::NO_SERIALIZATION,
        CompressionType::GZIP
    );

    AppendU32(frame, 500);

    // 添加非法 GZIP 数据
    std::vector<uint8_t> bad_gzip = {0xDE, 0xAD, 0xBE, 0xEF};
    AppendU32(frame, static_cast<uint32_t>(bad_gzip.size()));
    frame.insert(frame.end(), bad_gzip.begin(), bad_gzip.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert - 解压失败应返回空结果
    EXPECT_TRUE(result.message_type.empty());
}

// ==================== 测试：特殊字符和 Unicode ====================

TEST_F(ProtocolTest, BuildFullRequest_UnicodeSessionId) {
    // Arrange - session_id 包含 Unicode 字符
    uint32_t event = events::START_SESSION;
    std::string session_id = "会话-测试-🎤";
    nlohmann::json payload = {{"language", "zh-CN"}};

    // Act
    auto request = Protocol::BuildFullRequest(event, session_id, payload);

    // Assert
    ASSERT_GE(request.size(), 4);
    
    // 验证 session_id 长度（UTF-8 字节数）
    uint32_t session_id_len = Protocol::ReadUint32BigEndian(request.data() + 8);
    EXPECT_EQ(session_id_len, session_id.size());
}

TEST_F(ProtocolTest, CompressGzip_UnicodeData) {
    // Arrange
    std::string original = "这是中文测试数据 🎵🎶";
    std::vector<uint8_t> data(original.begin(), original.end());

    // Act
    auto compressed = Protocol::CompressGzip(data);
    auto decompressed = Protocol::DecompressGzip(compressed);

    // Assert
    std::string result(decompressed.begin(), decompressed.end());
    EXPECT_EQ(result, original);
}

// ==================== 测试：大数据量 ====================

TEST_F(ProtocolTest, ParseResponse_LargeJsonPayload) {
    // Arrange - 大 JSON payload
    auto frame = BuildServerFrame(
        MessageType::SERVER_FULL_RESPONSE,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION
    );

    AppendU32(frame, events::ASR_RESULT);
    AppendString(frame, "large-session");

    // 创建大 JSON
    nlohmann::json payload = nlohmann::json::array();
    for (int i = 0; i < 1000; ++i) {
        payload.push_back({{"index", i}, {"data", "item-" + std::to_string(i)}});
    }
    std::string payload_str = payload.dump();
    AppendU32(frame, static_cast<uint32_t>(payload_str.size()));
    frame.insert(frame.end(), payload_str.begin(), payload_str.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_FULL_RESPONSE");
    EXPECT_TRUE(result.payload.is_array());
    EXPECT_EQ(result.payload.size(), 1000);
}

TEST_F(ProtocolTest, BuildClientAudioRequest_VeryLargeAudio) {
    // Arrange - 1MB 音频数据
    uint32_t event = events::TASK_REQUEST;
    std::string session_id = "large-audio-session";
    std::vector<uint8_t> audio_data(1024 * 1024, 0x80); // 1MB

    // Act
    auto request = Protocol::BuildClientAudioRequest(event, session_id, audio_data);

    // Assert
    size_t expected_size = 4 + 4 + 4 + session_id.size() + 4 + audio_data.size();
    EXPECT_EQ(request.size(), expected_size);
}

// ==================== 测试：NO_SERIALIZATION 模式 ====================

TEST_F(ProtocolTest, ParseResponse_NoSerialization_BinaryPayload) {
    // Arrange - NO_SERIALIZATION 应直接返回二进制数据
    auto frame = BuildServerFrame(
        MessageType::SERVER_ACK,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::NO_SERIALIZATION,
        CompressionType::NO_COMPRESSION
    );

    AppendU32(frame, events::TTS_START);
    AppendString(frame, "binary-session");

    // 添加二进制 payload（PCM 音频样本）
    std::vector<uint8_t> binary_payload = {
        0x00, 0x80, 0xFF, 0x7F, 0x12, 0x34, 0x56, 0x78
    };
    AppendU32(frame, static_cast<uint32_t>(binary_payload.size()));
    frame.insert(frame.end(), binary_payload.begin(), binary_payload.end());

    // Act
    auto result = Protocol::ParseResponse(frame);

    // Assert
    EXPECT_EQ(result.message_type, "SERVER_ACK");
    EXPECT_TRUE(result.is_binary);
    EXPECT_EQ(result.payload_bytes, binary_payload);
}

// ==================== 主函数 ====================

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
