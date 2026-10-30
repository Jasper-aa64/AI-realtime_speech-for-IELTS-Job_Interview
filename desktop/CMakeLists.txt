cmake_minimum_required(VERSION 3.21)
project(IELTSStudioDesktop VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTORCC ON)

find_package(Qt6 6.8 REQUIRED COMPONENTS Widgets WebEngineWidgets WebChannel Test)
qt_standard_project_setup()

add_library(studio_core STATIC
    src/server_settings.cpp src/server_settings.h
    src/navigation_policy.cpp src/navigation_policy.h
    src/error_page.cpp src/error_page.h
    src/studio_profile.cpp src/studio_profile.h
    src/studio_page.cpp src/studio_page.h
    src/browser_window.cpp src/browser_window.h
    src/native_bridge.cpp src/native_bridge.h
    src/popup_relay.cpp src/popup_relay.h
    src/voice_bridge.cpp src/voice_bridge.h
    src/voice_settings.cpp src/voice_settings.h
)
target_include_directories(studio_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(studio_core PUBLIC Qt6::Widgets Qt6::WebEngineWidgets Qt6::WebChannel)

set(STUDIO_BUNDLE_ICON assets/studio-brain.icns)
set_source_files_properties(${STUDIO_BUNDLE_ICON} PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
qt_add_executable(IELTSStudio MACOSX_BUNDLE src/main.cpp resources.qrc ${STUDIO_BUNDLE_ICON})
set_target_properties(IELTSStudio PROPERTIES
    OUTPUT_NAME "IELTS Studio"
    MACOSX_BUNDLE_INFO_PLIST ${CMAKE_CURRENT_SOURCE_DIR}/Info.plist.in
    MACOSX_BUNDLE_GUI_IDENTIFIER com.ieltsstudio.desktop
    MACOSX_BUNDLE_BUNDLE_NAME "IELTS Studio"
    MACOSX_BUNDLE_ICON_FILE "studio-brain.icns"
    MACOSX_BUNDLE_BUNDLE_VERSION ${PROJECT_VERSION}
    MACOSX_BUNDLE_SHORT_VERSION_STRING ${PROJECT_VERSION}
)
target_compile_definitions(IELTSStudio PRIVATE STUDIO_VERSION="${PROJECT_VERSION}")
# Realtime voice engine (Boost.Beast, OpenSSL, PortAudio, spdlog, nlohmann_json) shared with the root project.
# Configure with the vcpkg toolchain (classic mode) as in desktop/README.md.
include(${CMAKE_CURRENT_SOURCE_DIR}/../cmake/voice_engine.cmake)
add_library(studio_voice STATIC src/realtime_voice_engine.cpp src/realtime_voice_engine.h)
target_link_libraries(studio_voice PUBLIC studio_core PRIVATE voice_engine)
target_link_libraries(IELTSStudio PRIVATE studio_core studio_voice voice_engine spdlog::spdlog)

enable_testing()

function(studio_test name)
    qt_add_executable(${name} tests/${name}.cpp)
    target_link_libraries(${name} PRIVATE studio_core Qt6::Test)
    add_test(NAME ${name} COMMAND ${name})
    set_tests_properties(${name} PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endfunction()

studio_test(server_settings_test)
studio_test(navigation_policy_test)
studio_test(error_page_test)
studio_test(native_bridge_test)
