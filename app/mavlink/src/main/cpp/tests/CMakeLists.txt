# Host (Linux/WSL) tests for the mavlink module's device-free code.
#   cmake -S app/mavlink/src/main/cpp/tests -B /tmp/mavlink-tests
#   cmake --build /tmp/mavlink-tests -j8 && (cd /tmp/mavlink-tests && ctest --output-on-failure)
cmake_minimum_required(VERSION 3.14)
project(MavlinkHostTests LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)
FetchContent_Declare(googletest URL https://github.com/google/googletest/archive/refs/tags/v1.14.0.zip)
set(gtest_force_shared_crt OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)
enable_testing()

add_executable(listener_lifecycle_test ListenerLifecycle_test.cpp)
target_include_directories(listener_lifecycle_test PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/..)
target_link_libraries(listener_lifecycle_test GTest::gtest_main pthread)
include(GoogleTest)
gtest_discover_tests(listener_lifecycle_test)

add_executable(home_position_test HomePosition_test.cpp)
target_include_directories(home_position_test PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/..)
target_link_libraries(home_position_test GTest::gtest_main)
gtest_discover_tests(home_position_test)
