#include "common/protocol.h"
#include <zlib.h>
#include <stdexcept>
#include <cstring>
#include <bitset>
#include "common/logger.h"

namespace interview {
namespace common {

// uint8_t转换为4位二进制字符串格式
inline std::string ToBinary4(uint8_t value) {
    return "0b" + std::bitset<4>(value).to_string();
}

// uint8_t转换为完整8位二进制字符串
inline std::string ToBinary8(uint8_t value) {
    return "0b" + std::bitset<8>(value).to_string();
}

ProtocolHeader::ProtocolHeader()
    : version(PROTOCOL_VERSION)
    , header_size(DEFAULT_HEADER_SIZE)
    , message_type(MessageType::CLIENT_FULL_REQUEST)
    , flags(MessageFlags::MSG_WITH_EVENT)
    , serialization(SerializationMethod::JSON)
    , compression(CompressionType::NO_COMPRESSION)
    , reserved(0) {
}

std::vector<uint8_t> Protocol::GenerateHeader(
    MessageType message_type,
    MessageFlags flags,
    SerializationMethod serialization,
    CompressionType compression,
    uint8_t reserved) 
{
    // 协议头编码逻辑
    std::vector<uint8_t> header;
    // 第1字节: version(4bits) + header_size(4bits)
    header.push_back((PROTOCOL_VERSION << 4) | DEFAULT_HEADER_SIZE);
    // 第2字节: message_type(4bits) + flags(4bits)
    header.push_back(static_cast<uint8_t>(message_type) << 4 | static_cast<uint8_t>(flags));
    // 第3字节: serialization(4bits) + compression(4bits)
    header.push_back((static_cast<uint8_t>(serialization) << 4) | static_cast<uint8_t>(compression));
    // 第4字节: reserved
    header.push_back(reserved);
    return header;
}

/**
* @brief 解析服务器响应
*
* 从接收到的二进制数据中解析出协议头、事件、payload等信息。 保存解析出的所有字段
* 支持多种消息类型：
* - SERVER_FULL_RESPONSE: 包含JSON payload的完整响应（事件通知）
* - SERVER_ACK: 确认消息，可能包含音频数据（TTS音频流）
* - SERVER_ERROR_RESPONSE: 错误响应，包含错误码和错误消息
*
* 解析流程：
* 1. 解析协议头（4字节）
* 2. 根据flags解析序列号（可选）
* 3. 根据flags解析事件编号（可选）
* 4. 根据事件类型解析session_id（可选）
* 5. 根据事件类型解析connect_id（可选）
* 6. 解析payload大小和数据
* 7. 根据压缩类型解压payload
* 8. 根据序列化方法反序列化payload
*
* @param data 接收到的完整二进制数据
* @return 解析后的响应结构，包含所有字段
*/
//从接收到的二进制数据中解析出协议头、事件、payload等信息。 保存解析出的所有字段
ParsedResponse Protocol::ParseResponse(const std::vector<uint8_t>& data) {
    // 实现服务端响应解析逻辑
    ParsedResponse result;
    if(data.size() < 4) {
        LOG_ERROR("ParseResponse: Data too short (", data.size(), " bytes), need at least 4 bytes for header");
        return result;
    }
    // 解析协议头
    uint8_t version = data[0] >> 4;
    uint8_t header_size = data[0] & 0x0F;
    MessageType message_type = static_cast<MessageType>((data[1] >> 4) & 0x0F);
    MessageFlags message_flags = static_cast<MessageFlags>((data[1] & 0x0F));
    SerializationMethod serialization = static_cast<SerializationMethod>((data[2] >> 4) & 0x0F);
    CompressionType compression = static_cast<CompressionType>((data[2] & 0x0F));
    
    size_t payload_start = 4*header_size;
    if(payload_start >= data.size()) {
        LOG_ERROR("ParseResponse: Payload start index (", payload_start, ") is out of bounds (", data.size(), " bytes)");
        return result;
    }

    const uint8_t* payload_ptr = data.data() + payload_start;
    size_t payload_size = data.size() - payload_start;
    size_t offset = 0;
    
    //判断消息类型
    if (message_type == (MessageType::SERVER_FULL_RESPONSE) ||
        message_type == (MessageType::SERVER_ACK)) {
        // 暂存消息类型字符串，只有在解析完全成功后才设置到 result
        std::string msg_type_str = (message_type == MessageType::SERVER_ACK)
            ? "SERVER_ACK" : "SERVER_FULL_RESPONSE";

        // 1. 解析序列号（如果flags中包含）
        if (ContainsSequence(static_cast<uint8_t>(message_flags))) {
            if(payload_size < 4+offset) {
                LOG_ERROR("Not enough bytes for sequence at offset ", offset);
                return ParsedResponse{};  // 返回空结果
            }
            result.sequence = ReadInt32BigEndian(payload_ptr + offset);
            offset += 4;
        }

        // 2. 解析事件编号（如果flags中包含）
        if (ContainsEvent(static_cast<uint8_t>(message_flags))) {
            if(payload_size < 4+offset) {
                LOG_ERROR("Not enough bytes for event at offset ", offset);
                return ParsedResponse{};
            }
            result.event = ReadUint32BigEndian(payload_ptr + offset);
            offset += 4;

            // 3. 解析session_id（根据event判断是否跳过）
            if ( !ShouldSkipSessionID(result.event) ) {
                if(payload_size < 4+offset) {
                    LOG_ERROR("Not enough bytes for session_id length at offset ", offset);
                    return ParsedResponse{};
                }
                uint32_t session_id_size = ReadUint32BigEndian(payload_ptr + offset);
                offset += 4;

                if(payload_size < session_id_size+offset) {
                    LOG_ERROR("Not enough bytes for session_id data at offset ", offset);
                    return ParsedResponse{};
                }
                result.session_id = std::string(reinterpret_cast<const char*>(payload_ptr + offset), session_id_size);
                offset += session_id_size;
            }

            // 4. 解析connect_id（如果是连接相关事件）
            if (ShouldReadConnectID(result.event)) {
                if (payload_size < 4+offset) {
                    LOG_ERROR("Not enough bytes for connect_id length at offset ", offset);
                    return ParsedResponse{};
                }
                uint32_t connect_id_size = ReadUint32BigEndian(payload_ptr + offset);
                offset += 4;

                if (payload_size < connect_id_size+offset) {
                    LOG_ERROR("Not enough bytes for connect_id data at offset ", offset);
                    return ParsedResponse{};
                }
                result.connect_id = std::string(reinterpret_cast<const char*>(payload_ptr + offset), connect_id_size);
                offset += connect_id_size;
            }
        }

        // 5. 解析payload大小和数据
        if(payload_size < 4+offset) {
            LOG_ERROR("Not enough bytes for payload size at offset ", offset);
            return ParsedResponse{};
        }
        result.payload_size = ReadUint32BigEndian(payload_ptr + offset);
        offset += 4;

        if(payload_size < result.payload_size+offset) {
            LOG_ERROR("Not enough bytes for payload data at offset ", offset);
            return ParsedResponse{};
        }
        
        std::vector<uint8_t> payload_data(
            payload_ptr + offset,
            payload_ptr + offset + result.payload_size
        );
        
        // 解压
        if (compression == CompressionType::GZIP){
            try {
                payload_data = DecompressGzip(payload_data);
            } catch (const std::exception& e) {
                LOG_ERROR("GZIP decompression failed: ", e.what());
                return ParsedResponse{};
            }
        }

        // 反序列化
        if (serialization == SerializationMethod::JSON) {
            try {
                std::string json_str(payload_data.begin(), payload_data.end());
                result.payload = nlohmann::json::parse(json_str);
                result.is_binary = false;
            } catch (const std::exception& e) {
                LOG_WARNING("JSON parsing failed: ", e.what(), " - treating as binary data");
                result.is_binary = true;
                result.payload_bytes = payload_data;
            }
        }
        else if (serialization == SerializationMethod::NO_SERIALIZATION){
            result.is_binary = true;
            result.payload_bytes = payload_data;
        }
        else{
            LOG_ERROR("Unsupported serialization method: ", ToBinary4(static_cast<uint8_t>(serialization)), " (", static_cast<int>(serialization), ")");
            return ParsedResponse{};
        }
        
        // 解析成功，设置消息类型
        result.message_type = msg_type_str;
    }
    else if (message_type == MessageType::SERVER_ERROR_RESPONSE ) {
        // 错误响应: error_code + payload_size + payload
        if (payload_size < 4+offset) {
            LOG_ERROR("Not enough bytes for error_code at offset ", offset);
            return ParsedResponse{};
        }
        result.code = ReadUint32BigEndian(payload_ptr + offset);
        offset += 4;

        if (payload_size < offset + 4) {
            LOG_ERROR("Not enough bytes for error payload size");
            return ParsedResponse{};
        }
        result.payload_size = ReadUint32BigEndian(payload_ptr + offset);
        offset += 4;

        if (payload_size < offset + result.payload_size) {
            LOG_ERROR("Not enough bytes for error payload data");
            return ParsedResponse{};
        }
        std::vector<uint8_t> payload_data(
            payload_ptr + offset,
            payload_ptr + offset + result.payload_size
        );

        if (compression == CompressionType::GZIP) {
            try {
                payload_data = DecompressGzip(payload_data);
            } catch (const std::exception& e) {
                LOG_ERROR("GZIP decompression failed: ", e.what());
                return ParsedResponse{};
            }
        }

        std::string error_msg(payload_data.begin(), payload_data.end());
        result.payload = nlohmann::json{{"error", error_msg}};
        
        // 解析成功，设置消息类型
        result.message_type = "SERVER_ERROR";
    }
    else{
        LOG_ERROR("ParseResponse: Unsupported message type: ", ToBinary4(static_cast<uint8_t>(message_type)), " (", static_cast<int>(message_type), ")");
    }

    return result;
}

std::vector<uint8_t> Protocol::CompressGzip(const std::vector<uint8_t>& data) {
    // z_stream{} 零初始化，确保 zalloc/zfree/opaque 为 Z_NULL（zlib 要求）
    z_stream stream{};

    // windowBits = 15 + 16：15 位滑动窗口 + 16 表示输出 GZIP 格式（而非裸 deflate）
    // memlevel = 8：默认内存使用级别
    // Z_BEST_SPEED：实时通信场景优先压缩速度而非压缩率
    const int init_ret = deflateInit2(
        &stream,
        Z_BEST_SPEED,
        Z_DEFLATED,
        15 + 16,
        8,
        Z_DEFAULT_STRATEGY);

    if (init_ret != Z_OK) {
        throw std::runtime_error("CompressGzip: failed to initialize zlib");
    }

    // deflateBound 返回压缩后数据的最大可能大小，一次性预分配避免动态扩容
    std::vector<uint8_t> compressed;
    compressed.resize(deflateBound(&stream, static_cast<uLong>(data.size())));

    stream.next_in  = const_cast<Bytef*>(reinterpret_cast<const Bytef*>(data.data()));
    stream.avail_in = static_cast<uInt>(data.size());
    stream.next_out  = reinterpret_cast<Bytef*>(compressed.data());
    stream.avail_out = static_cast<uInt>(compressed.size());

    // Z_FINISH：一次性完成所有输入的压缩并写入结尾标记
    // 由于输出缓冲区由 deflateBound 保证足够大，单次调用必然返回 Z_STREAM_END
    const int ret = deflate(&stream, Z_FINISH);
    if (ret != Z_STREAM_END) {
        deflateEnd(&stream);  // 异常路径也必须释放 zlib 内部资源
        throw std::runtime_error("CompressGzip: zlib deflate failed");
    }

    // stream.total_out 是实际写入的压缩字节数，裁剪掉预分配的多余空间
    compressed.resize(stream.total_out);
    deflateEnd(&stream);
    return compressed;
}

std::vector<uint8_t> Protocol::DecompressGzip(const std::vector<uint8_t>& data) {
    if (data.empty()) {
        return {};
    }

    z_stream stream{};
    const int init_ret = inflateInit2(&stream, 15 + 16);  // 15-bit window + gzip header/trailer
    if (init_ret != Z_OK) {
        throw std::runtime_error("DecompressGzip: failed to initialize zlib");
    }

    stream.next_in = const_cast<Bytef*>(reinterpret_cast<const Bytef*>(data.data()));
    stream.avail_in = static_cast<uInt>(data.size());

    // 预估容量，尽量减少扩容次数；小包至少给 1KB。
    std::vector<uint8_t> decompressed;
    const size_t initial_capacity = (data.size() * 3 > 1024) ? data.size() * 3 : 1024;
    decompressed.resize(initial_capacity);

    int ret = Z_OK;
    do {
        if (stream.total_out == decompressed.size()) {
            decompressed.resize(decompressed.size() * 2);
        }

        stream.next_out = reinterpret_cast<Bytef*>(decompressed.data() + stream.total_out);
        stream.avail_out = static_cast<uInt>(decompressed.size() - stream.total_out);

        ret = inflate(&stream, Z_NO_FLUSH);
        if (ret != Z_OK && ret != Z_STREAM_END) {
            inflateEnd(&stream);
            throw std::runtime_error("DecompressGzip: zlib inflate failed");
        }
    } while (ret != Z_STREAM_END);

    decompressed.resize(stream.total_out);
    inflateEnd(&stream);
    return decompressed;
}

void Protocol::AppendUint32BigEndian(std::vector<uint8_t>& buffer, uint32_t value) {
    // 按网络字节序（大端）写入：高字节在前，低字节在后
    buffer.push_back(static_cast<uint8_t>((value >> 24) & 0xFF));
    buffer.push_back(static_cast<uint8_t>((value >> 16) & 0xFF));
    buffer.push_back(static_cast<uint8_t>((value >> 8) & 0xFF));
    buffer.push_back(static_cast<uint8_t>(value & 0xFF));
}

uint32_t Protocol::ReadUint32BigEndian(const uint8_t* data) {
    return (static_cast<uint32_t>(data[0]) << 24) |
           (static_cast<uint32_t>(data[1]) << 16) |
           (static_cast<uint32_t>(data[2]) << 8) |
           static_cast<uint32_t>(data[3]);
}

int32_t Protocol::ReadInt32BigEndian(const uint8_t* data) {
    const uint32_t raw = ReadUint32BigEndian(data);
    int32_t value;
    std::memcpy(&value, &raw, sizeof(value));
    return value;
}

bool Protocol::ContainsSequence(uint8_t message_flags) {
    // 检查flags中是否设置了POS_SEQUENCE或NEG_SEQUENCE位
    constexpr uint8_t POS_SEQ = static_cast<uint8_t>(MessageFlags::POS_SEQUENCE);
    constexpr uint8_t NEG_SEQ = static_cast<uint8_t>(MessageFlags::NEG_SEQUENCE);
    return (message_flags & POS_SEQ) == POS_SEQ || (message_flags & NEG_SEQ) == NEG_SEQ;
}

bool Protocol::ContainsEvent(uint8_t message_flags) {
    // 检查flags中是否设置了MSG_WITH_EVENT位
    constexpr uint8_t EVENT = static_cast<uint8_t>(MessageFlags::MSG_WITH_EVENT);
    return (message_flags & EVENT) == EVENT;
}

bool Protocol::ShouldSkipSessionID(uint32_t event) {
    // 事件1,2,50,51,52不包含session_id
    // 1=StartConnection, 2=FinishConnection,
    // 50=ConnectionStarted, 51=ConnectionFailed, 52=ConnectionFinished
    switch (event) {
        case events::START_CONNECTION:
        case events::FINISH_CONNECTION:
        case events::CONNECTION_STARTED:
        case events::CONNECTION_FAILED:
        case events::CONNECTION_FINISHED:
            return true;
        default:
            return false;
    }
}

bool Protocol::ShouldReadConnectID(uint32_t event) {
    // 事件50,51,52包含connect_id
    // 50=ConnectionStarted, 51=ConnectionFailed, 52=ConnectionFinished
    return event == events::CONNECTION_STARTED ||
           event == events::CONNECTION_FAILED ||
           event == events::CONNECTION_FINISHED;
}

std::vector<uint8_t> Protocol::BuildFullRequest(
    uint32_t event,
    const std::string& session_id,
    const nlohmann::json& payload) {
    // 完整请求使用 JSON、无压缩：减少 CPU 开销，优先实时性。
    std::string payload_str = payload.dump();
    std::vector<uint8_t> payload_bytes(payload_str.begin(), payload_str.end());

    const bool skip_session_id = ShouldSkipSessionID(event);
    const size_t session_part_size = skip_session_id ? 0 : (4 + session_id.size());
    const size_t total_size = 4 + 4 + session_part_size + 4 + payload_bytes.size();

    std::vector<uint8_t> request;
    request.reserve(total_size);

    // 1) 协议头：客户端完整请求 + 含事件 + JSON + 不压缩
    auto header = GenerateHeader(
        MessageType::CLIENT_FULL_REQUEST,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::JSON,
        CompressionType::NO_COMPRESSION,
        0x00);
    request.insert(request.end(), header.begin(), header.end());

    // 2) event
    AppendUint32BigEndian(request, event);

    // 3) session_id（连接控制事件不携带）
    if (!skip_session_id) {
        AppendUint32BigEndian(request, static_cast<uint32_t>(session_id.size()));
        request.insert(request.end(), session_id.begin(), session_id.end());
    }

    // 4) payload
    AppendUint32BigEndian(request, static_cast<uint32_t>(payload_bytes.size()));
    request.insert(request.end(), payload_bytes.begin(), payload_bytes.end());

    return request;
}

std::vector<uint8_t> Protocol::BuildClientAudioRequest(
    uint32_t event,
    const std::string& session_id,
    const std::vector<uint8_t>& audio_data) {
    const bool skip_session_id = ShouldSkipSessionID(event);
    const size_t session_part_size = skip_session_id ? 0 : (4 + session_id.size());
    const size_t total_size = 4 + 4 + session_part_size + 4 + audio_data.size();

    std::vector<uint8_t> request;
    request.reserve(total_size);

    // 1. 添加协议头（音频请求不使用JSON序列化）
    auto header = GenerateHeader(
        MessageType::CLIENT_AUDIO_ONLY_REQUEST,
        MessageFlags::MSG_WITH_EVENT,
        SerializationMethod::NO_SERIALIZATION,
        CompressionType::NO_COMPRESSION,
        0x00);
    request.insert(request.end(), header.begin(), header.end());

    // 2. 添加event (4字节大端)
    AppendUint32BigEndian(request, event);

    // 3. 添加session_id长度和内容（根据event类型判断是否需要）
    if (!skip_session_id) {
        AppendUint32BigEndian(request, static_cast<uint32_t>(session_id.size()));
        request.insert(request.end(), session_id.begin(), session_id.end());
    }

    // 4. 添加音频数据（不压缩）
    // 5. 添加payload大小和内容
    AppendUint32BigEndian(request, static_cast<uint32_t>(audio_data.size()));
    request.insert(request.end(), audio_data.begin(), audio_data.end());

    return request;
}

} // namespace common
} // namespace interview
