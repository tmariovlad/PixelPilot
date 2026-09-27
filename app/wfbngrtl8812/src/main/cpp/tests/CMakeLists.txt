# Host (Linux/WSL) tests for wfbngrtl8812 code that needs no USB device. Needs libsodium (pkg-config).
#   cmake -S app/wfbngrtl8812/src/main/cpp/tests -B /tmp/wfbng-tests
#   cmake --build /tmp/wfbng-tests -j8 && (cd /tmp/wfbng-tests && ctest --output-on-failure)
cmake_minimum_required(VERSION 3.14)
project(WfbngHostTests LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(SRC ${CMAKE_CURRENT_SOURCE_DIR}/..)
# The NDK logging stand-in already used by the videonative host tests (single copy).
set(LOG_SHIM ${SRC}/../../../../videonative/src/main/cpp/tests/host_shim)

include(FetchContent)
FetchContent_Declare(googletest URL https://github.com/google/googletest/archive/refs/tags/v1.14.0.zip)
set(gtest_force_shared_crt OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)
enable_testing()

find_package(PkgConfig REQUIRED)
pkg_check_modules(sodium REQUIRED IMPORTED_TARGET libsodium)

add_executable(txframe_test
    TxFrame_test.cpp
    ${SRC}/TxFrame.cpp
    ${SRC}/wfb-ng/src/wifibroadcast.cpp
    ${SRC}/wfb-ng/src/zfex.c)
target_include_directories(txframe_test PRIVATE ${LOG_SHIM} ${CMAKE_CURRENT_SOURCE_DIR}/host_shim ${SRC} ${SRC}/wfb-ng ${SRC}/devourer)
target_link_libraries(txframe_test PkgConfig::sodium GTest::gtest_main pthread)
include(GoogleTest)
gtest_discover_tests(txframe_test)

add_executable(stats_window_test StatsWindow_test.cpp)
target_include_directories(stats_window_test PRIVATE ${SRC})
target_link_libraries(stats_window_test GTest::gtest_main)
gtest_discover_tests(stats_window_test)

add_executable(link_guard_test LinkGuard_test.cpp)
target_include_directories(link_guard_test PRIVATE ${SRC})
target_link_libraries(link_guard_test GTest::gtest_main)
gtest_discover_tests(link_guard_test)
