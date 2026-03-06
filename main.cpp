function(add_formatted_target target_name)​
    add_executable(${target_name} ${ARGN})​
    target_compile_options(${target_name} PRIVATE -Wall -Wextra)​
    set_target_properties(${target_name} PROPERTIES CXX_STANDARD 17)​
endfunction()​
​
# 使用自定义函数​
add_formatted_target(app1 app1.cpp)​
add_formatted_target(app2 app2.cpp utils.cpp)