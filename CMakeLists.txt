cmake_minimum_required(VERSION 3.16)

project(AIProject)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

enable_testing()

# vcpkg 库路径
set(VCPKG_LOCAL  "${PROJECT_SOURCE_DIR}/vcpkg_installed/arm64-osx")
set(VCPKG_GLOBAL "$ENV{HOME}/Desktop/CS/Cplusplus/vcpkg/installed/arm64-osx")

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
