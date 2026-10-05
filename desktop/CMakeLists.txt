cmake_minimum_required(VERSION 3.21)
project(IELTSStudioDesktop VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Qt6 6.8 REQUIRED COMPONENTS Widgets WebEngineWidgets Test)
qt_standard_project_setup()

add_library(studio_core STATIC
    src/server_settings.cpp src/server_settings.h
)
target_include_directories(studio_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(studio_core PUBLIC Qt6::Widgets Qt6::WebEngineWidgets)

enable_testing()

function(studio_test name)
    qt_add_executable(${name} tests/${name}.cpp)
    target_link_libraries(${name} PRIVATE studio_core Qt6::Test)
    add_test(NAME ${name} COMMAND ${name})
    set_tests_properties(${name} PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endfunction()

studio_test(server_settings_test)
