cmake_minimum_required(VERSION 3.16)

project(AIProject)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

enable_testing()

# vcpkg 库路径
set(VCPKG_LOCAL  "${PROJECT_SOURCE_DIR}/vcpkg_installed/arm64-osx")
set(VCPKG_GLOBAL "$ENV{HOME}/Desktop/CS/Cplusplus/vcpkg/installed/arm64-osx")
list(PREPEND CMAKE_PREFIX_PATH "${VCPKG_LOCAL}")

# ==================== Config Test ====================

add_executable(
    config_test
    tests/config_test.cpp
    src/common/config.cpp
)

target_include_directories(
    config_test
    PRIVATE
    ${VCPKG_LOCAL}/include
    ${PROJECT_SOURCE_DIR}/include
    ${PROJECT_SOURCE_DIR}/src
)

target_link_libraries(
    config_test
    PRIVATE
    ${VCPKG_GLOBAL}/lib/libgtest.a
)

target_compile_definitions(
    config_test
    PRIVATE PROJECT_ROOT="${PROJECT_SOURCE_DIR}"
)

add_test(
    NAME config_test
    COMMAND config_test
)

# ==================== Protocol Test ====================

add_executable(
    protocol_test
    tests/protocol_test.cpp
    src/common/protocol.cpp
    src/common/logger.cpp
)

target_include_directories(
    protocol_test
    PRIVATE
    ${VCPKG_LOCAL}/include
    ${VCPKG_GLOBAL}/include
    ${PROJECT_SOURCE_DIR}/include
    ${PROJECT_SOURCE_DIR}/src
)

target_link_libraries(
    protocol_test
    PRIVATE
    ${VCPKG_GLOBAL}/lib/libgtest.a
    ${VCPKG_LOCAL}/lib/libspdlog.a
    ${VCPKG_LOCAL}/lib/libfmt.a
    ${VCPKG_LOCAL}/lib/libz.a
)

add_test(
    NAME protocol_test
    COMMAND protocol_test
)

# ==================== Logger Test ====================

add_executable(
    logger_test
    tests/logger_test.cpp
    src/common/logger.cpp
)

target_include_directories(
    logger_test
    PRIVATE
    ${VCPKG_LOCAL}/include
    ${VCPKG_GLOBAL}/include
    ${PROJECT_SOURCE_DIR}/include
    ${PROJECT_SOURCE_DIR}/src
)

target_link_libraries(
    logger_test
    PRIVATE
    ${VCPKG_GLOBAL}/lib/libgtest.a
    ${VCPKG_LOCAL}/lib/libspdlog.a
    ${VCPKG_LOCAL}/lib/libfmt.a
)

add_test(
    NAME logger_test
    COMMAND logger_test
)

# ==================== Services Test ====================

find_package(spdlog CONFIG REQUIRED)
find_package(CURL CONFIG REQUIRED)
find_package(podofo CONFIG REQUIRED)
find_package(portaudio CONFIG REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(BZip2 REQUIRED)
find_package(LibLZMA REQUIRED)
find_package(unofficial-brotli CONFIG REQUIRED)
find_package(expat CONFIG REQUIRED)
find_package(Iconv REQUIRED)
find_package(boost_thread CONFIG REQUIRED)
find_package(boost_chrono CONFIG REQUIRED)
find_package(boost_date_time CONFIG REQUIRED)
find_package(boost_atomic CONFIG REQUIRED)

add_executable(
    services_test
    tests/services_test.cpp
    src/services/audio_manager.cpp
    src/services/llm_client.cpp
    src/services/pdf_parser.cpp
    src/services/realtime_client.cpp
    src/common/config.cpp
    src/common/logger.cpp
    src/common/protocol.cpp
)

target_include_directories(
    services_test
    PRIVATE
    ${VCPKG_LOCAL}/include
    ${VCPKG_GLOBAL}/include
    ${PROJECT_SOURCE_DIR}/include
    ${PROJECT_SOURCE_DIR}/src
)

target_link_libraries(
    services_test
    PRIVATE
    ${VCPKG_GLOBAL}/lib/libgtest.a
    spdlog::spdlog
    podofo::podofo
    CURL::libcurl
    portaudio_static
    OpenSSL::SSL
    OpenSSL::Crypto
    BZip2::BZip2
    LibLZMA::LibLZMA
    unofficial::brotli::brotlidec
    expat::expat
    Iconv::Iconv
    Boost::thread
    Boost::chrono
    Boost::date_time
    Boost::atomic
)

target_compile_definitions(
    services_test
    PRIVATE PROJECT_ROOT="${PROJECT_SOURCE_DIR}"
)

add_test(
    NAME services_test
    COMMAND services_test
)
