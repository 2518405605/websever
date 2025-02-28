# 设置 CMake 最低版本要求
cmake_minimum_required(VERSION 3.0) 

# 设置项目名称
project(eric)  

# 开启详细的 Makefile 输出
set(CMAKE_VERBOSE_MAKEFILE ON) 

# 设置 C++ 编译选项
set(CMAKE_CXX_FLAGS "$ENV{CXX_FLAGS} -rdynamic -O3 -g -std=c++11 -Wall -Wno-deprecated ") 

# 定义库的源文件列表
set(LIB_SRC
    ../log.cc
    ../util.cc
)

# 创建共享库
add_library(eric SHARED ${LIB_SRC})

# 创建静态库（注释部分，可按需启用）
# add_library(eric_static STATIC ${LIB_SRC})

# 设置库的输出名称（注释部分，可按需启用）
# SET_TARGET_PROPERTIES (eric PROPERTIES OUTPUT_NAME "eric")

# 创建可执行文件
add_executable(test ../tests/test.cc)

# 设置依赖关系，确保在构建 test 之前先构建 eric 库
add_dependencies(test eric)

# 将 eric 库链接到 test 可执行文件
target_link_libraries(test eric)

# 设置可执行文件的输出路径
SET(EXECUTABLE_OUTPUT_PATH ${PROJECT_SOURCE_DIR}/bin)

# 设置库的输出路径
SET(LIBRARY_OUTPUT_PATH ${PROJECT_SOURCE_DIR}/lib)