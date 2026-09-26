# Host (Linux/WSL) build of the station-mode code: unit tests always, and the go/no-go harness
# sta_ack_gate when a host build of devourer is given.
#
#   cmake -S app/wfbngrtl8812/src/main/cpp/sta/host -B /tmp/sta-host [-DDEVOURER_LIB=/tmp/devourer-build/libdevourer.a]
#   cmake --build /tmp/sta-host -j8 && (cd /tmp/sta-host && ctest --output-on-failure)
#
# devourer host library: cmake -S app/wfbngrtl8812/src/main/cpp/devourer -B /tmp/devourer-build -DCMAKE_BUILD_TYPE=Release
#                        cmake --build /tmp/devourer-build --target devourer -j16
cmake_minimum_required(VERSION 3.14)
project(StaHost LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(STA_DIR ${CMAKE_CURRENT_SOURCE_DIR}/..)
set(DEVOURER_DIR ${STA_DIR}/../devourer)

add_library(sta_frames STATIC ${STA_DIR}/StaFrames.cpp)
target_include_directories(sta_frames PUBLIC ${STA_DIR})

include(FetchContent)
FetchContent_Declare(googletest URL https://github.com/google/googletest/archive/refs/tags/v1.14.0.zip)
set(gtest_force_shared_crt OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)
enable_testing()

add_executable(sta_frames_test ${STA_DIR}/tests/StaFrames_test.cpp)
target_link_libraries(sta_frames_test sta_frames GTest::gtest_main)
include(GoogleTest)
gtest_discover_tests(sta_frames_test)

set(DEVOURER_LIB "" CACHE FILEPATH "host build of libdevourer.a; enables sta_ack_gate")
if(DEVOURER_LIB)
  find_package(PkgConfig REQUIRED)
  pkg_check_modules(libusb REQUIRED IMPORTED_TARGET libusb-1.0)
  add_executable(sta_ack_gate ${STA_DIR}/tools/sta_ack_gate.cpp ${DEVOURER_DIR}/examples/common/env_config.cpp)
  target_include_directories(sta_ack_gate PRIVATE ${DEVOURER_DIR}/src ${DEVOURER_DIR}/examples/common ${DEVOURER_DIR}/hal)
  target_link_libraries(sta_ack_gate sta_frames ${DEVOURER_LIB} PkgConfig::libusb pthread)
endif()
