cmake_minimum_required(VERSION 3.21)
project(IELTSStudioDesktop VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

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
)
target_include_directories(studio_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(studio_core PUBLIC Qt6::Widgets Qt6::WebEngineWidgets Qt6::WebChannel)

qt_add_executable(IELTSStudio MACOSX_BUNDLE src/main.cpp)
set_target_properties(IELTSStudio PROPERTIES
    OUTPUT_NAME "IELTS Studio"
    MACOSX_BUNDLE_INFO_PLIST ${CMAKE_CURRENT_SOURCE_DIR}/Info.plist.in
    MACOSX_BUNDLE_GUI_IDENTIFIER com.ieltsstudio.desktop
    MACOSX_BUNDLE_BUNDLE_NAME "IELTS Studio"
    MACOSX_BUNDLE_BUNDLE_VERSION ${PROJECT_VERSION}
    MACOSX_BUNDLE_SHORT_VERSION_STRING ${PROJECT_VERSION}
)
target_compile_definitions(IELTSStudio PRIVATE STUDIO_VERSION="${PROJECT_VERSION}")
target_link_libraries(IELTSStudio PRIVATE studio_core)

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
