cmake_minimum_required(VERSION 3.16)

project(AIProject)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

enable_testing()

# vcpkg 库路径
set(VCPKG_LOCAL  "${PROJECT_SOURCE_DIR}/vcpkg_installed/arm64-osx")
set(VCPKG_GLOBAL "$ENV{HOME}/Desktop/CS/Cplusplus/vcpkg/installed/arm64-osx")
list(PREPEND CMAKE_PREFIX_PATH "${VCPKG_LOCAL}")

# ==================== Application ====================

add_executable(
    CppInterviewSystem
    src/main.cpp
    src/interview/dialog_session.cpp
    src/interview/interview_manager.cpp
    src/services/audio_manager.cpp
    src/services/llm_client.cpp
    src/services/pdf_parser.cpp
    src/services/realtime_client.cpp
    src/common/config.cpp
    src/common/logger.cpp
    src/common/protocol.cpp
    src/common/interview_state.cpp
)

target_include_directories(
    CppInterviewSystem
    PRIVATE
    ${VCPKG_LOCAL}/include
    ${VCPKG_GLOBAL}/include
    ${PROJECT_SOURCE_DIR}/include
    ${PROJECT_SOURCE_DIR}/src
)

target_link_libraries(
    CppInterviewSystem
    PRIVATE
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

# ==================== Qt GUI Application ====================

find_package(Qt6 COMPONENTS Widgets QUIET)
if(NOT Qt6_FOUND)
    find_package(Qt5 COMPONENTS Widgets QUIET)
endif()

if(Qt6_FOUND OR Qt5_FOUND)
    if(Qt6_FOUND)
        set(QT_LIB Qt6::Widgets)
    else()
        set(QT_LIB Qt5::Widgets)
    endif()

    add_executable(
        CppInterviewSystemQt
        src/main_qt.cpp
        include/ui/mainwindow.h
        include/ui/config_dialog.h
        src/ui/mainwindow.cpp
        src/ui/config_dialog.cpp
        src/interview/dialog_session.cpp
        src/interview/interview_manager.cpp
        src/services/audio_manager.cpp
        src/services/llm_client.cpp
        src/services/pdf_parser.cpp
        src/services/realtime_client.cpp
        src/common/config.cpp
        src/common/logger.cpp
        src/common/protocol.cpp
        src/common/interview_state.cpp
    )

    target_include_directories(
        CppInterviewSystemQt
        PRIVATE
        ${VCPKG_LOCAL}/include
        ${VCPKG_GLOBAL}/include
        ${PROJECT_SOURCE_DIR}/include
        ${PROJECT_SOURCE_DIR}/src
    )

    target_link_libraries(
        CppInterviewSystemQt
        PRIVATE
        ${QT_LIB}
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
endif()

# ==================== IELTS CLI Application ====================

add_executable(
    IELTSSpeakingSimulator
    src/main_ielts.cpp
    src/ielts/ielts_manager.cpp
    src/ielts/part1_session.cpp
    src/ielts/part2_session.cpp
    src/ielts/part3_session.cpp
    src/ielts/question_bank.cpp
    src/ielts/scorer.cpp
    src/services/audio_manager.cpp
    src/services/llm_client.cpp
    src/services/realtime_client.cpp
    src/common/config.cpp
    src/common/logger.cpp
    src/common/protocol.cpp
    src/common/interview_state.cpp
)

target_include_directories(
    IELTSSpeakingSimulator
    PRIVATE
    ${VCPKG_LOCAL}/include
    ${VCPKG_GLOBAL}/include
    ${PROJECT_SOURCE_DIR}/include
    ${PROJECT_SOURCE_DIR}/src
)

target_link_libraries(
    IELTSSpeakingSimulator
    PRIVATE
    spdlog::spdlog
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
    IELTSSpeakingSimulator
    PRIVATE PROJECT_ROOT="${PROJECT_SOURCE_DIR}"
)

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
    ${VCPKG_GLOBAL}/include
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

# ==================== IELTS Data Test ====================

add_executable(
    ielts_data_test
    tests/ielts_data_test.cpp
    src/ielts/question_bank.cpp
    src/ielts/scorer.cpp
    src/common/logger.cpp
)

target_include_directories(
    ielts_data_test
    PRIVATE
    ${VCPKG_LOCAL}/include
    ${VCPKG_GLOBAL}/include
    ${PROJECT_SOURCE_DIR}/include
    ${PROJECT_SOURCE_DIR}/src
)

target_link_libraries(
    ielts_data_test
    PRIVATE
    ${VCPKG_GLOBAL}/lib/libgtest.a
    spdlog::spdlog
)

target_compile_definitions(
    ielts_data_test
    PRIVATE PROJECT_ROOT="${PROJECT_SOURCE_DIR}"
)

add_test(
    NAME ielts_data_test
    COMMAND ielts_data_test
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

# ==================== Interview Test ====================

add_executable(
    interview_test
    tests/interview_test.cpp
    src/interview/interview_manager.cpp
    src/services/llm_client.cpp
    src/services/pdf_parser.cpp
    src/common/config.cpp
    src/common/logger.cpp
)

target_include_directories(
    interview_test
    PRIVATE
    ${VCPKG_LOCAL}/include
    ${VCPKG_GLOBAL}/include
    ${PROJECT_SOURCE_DIR}/include
    ${PROJECT_SOURCE_DIR}/src
)

target_link_libraries(
    interview_test
    PRIVATE
    ${VCPKG_GLOBAL}/lib/libgtest.a
    spdlog::spdlog
    podofo::podofo
    CURL::libcurl
    OpenSSL::SSL
    OpenSSL::Crypto
    BZip2::BZip2
    LibLZMA::LibLZMA
    unofficial::brotli::brotlidec
    expat::expat
    Iconv::Iconv
)

add_test(
    NAME interview_test
    COMMAND interview_test
)
