# 实时语音引擎库 voice_engine：VoiceSession + RealtimeClient + PortAudio 设备。
# 不依赖 Qt、Django、面试内容。根项目和 desktop/ 都 include 这个文件。
# 依赖用 find_package 找（vcpkg classic 模式或 Homebrew 都行）：Boost.Beast/Asio、OpenSSL、ZLIB、
# spdlog、nlohmann_json、PortAudio。

if(TARGET voice_engine)
    return()
endif()

get_filename_component(VOICE_ENGINE_ROOT "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)

find_package(OpenSSL REQUIRED)
find_package(ZLIB REQUIRED)
find_package(spdlog CONFIG REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)
find_package(portaudio CONFIG REQUIRED)
find_package(boost_thread CONFIG REQUIRED)

add_library(voice_engine STATIC
    ${VOICE_ENGINE_ROOT}/src/voice/voice_session.cpp
    ${VOICE_ENGINE_ROOT}/src/voice/portaudio_device.cpp
    ${VOICE_ENGINE_ROOT}/src/voice/injecting_device.cpp
    ${VOICE_ENGINE_ROOT}/src/services/realtime_client.cpp
    ${VOICE_ENGINE_ROOT}/src/common/protocol.cpp
    ${VOICE_ENGINE_ROOT}/src/common/logger.cpp
    ${VOICE_ENGINE_ROOT}/src/common/config.cpp
)
set_target_properties(voice_engine PROPERTIES AUTOMOC OFF AUTOUIC OFF AUTORCC OFF POSITION_INDEPENDENT_CODE ON)
target_compile_features(voice_engine PUBLIC cxx_std_17)
target_include_directories(voice_engine
    PUBLIC ${VOICE_ENGINE_ROOT}/include
    PRIVATE ${VOICE_ENGINE_ROOT}/src)

if(TARGET portaudio_static)
    set(VOICE_ENGINE_PORTAUDIO portaudio_static)
else()
    set(VOICE_ENGINE_PORTAUDIO portaudio)
endif()

target_link_libraries(voice_engine
    PUBLIC nlohmann_json::nlohmann_json
    PRIVATE spdlog::spdlog ${VOICE_ENGINE_PORTAUDIO} OpenSSL::SSL OpenSSL::Crypto ZLIB::ZLIB Boost::thread)

# portaudio_device.cpp 在 macOS 上直接查 CoreAudio（默认输入是不是蓝牙耳机）
if(APPLE)
    target_link_libraries(voice_engine PRIVATE "-framework CoreAudio" "-framework CoreFoundation")
endif()
