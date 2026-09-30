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

add_executable(uplink_schedule_test UplinkSchedule_test.cpp)
target_include_directories(uplink_schedule_test PRIVATE ${SRC})
target_link_libraries(uplink_schedule_test GTest::gtest_main)
gtest_discover_tests(uplink_schedule_test)

add_executable(dec_err_probe_test DecErrProbe_test.cpp)
target_include_directories(dec_err_probe_test PRIVATE ${SRC})
target_link_libraries(dec_err_probe_test GTest::gtest_main)
gtest_discover_tests(dec_err_probe_test)

add_executable(signal_quality_test SignalQualityCalculator_test.cpp ${SRC}/SignalQualityCalculator.cpp)
target_include_directories(signal_quality_test PRIVATE ${LOG_SHIM} ${SRC})
target_link_libraries(signal_quality_test GTest::gtest_main)
gtest_discover_tests(signal_quality_test)

add_executable(rx_diag_test RxDiag_test.cpp)
target_include_directories(rx_diag_test PRIVATE ${SRC})
target_link_libraries(rx_diag_test GTest::gtest_main)
gtest_discover_tests(rx_diag_test)

add_executable(rx_rate_histogram_test RxRateHistogram_test.cpp)
target_include_directories(rx_rate_histogram_test PRIVATE ${SRC})
target_link_libraries(rx_rate_histogram_test GTest::gtest_main)
gtest_discover_tests(rx_rate_histogram_test)

add_executable(fec_block_probe_test FecBlockProbe_test.cpp)
target_include_directories(fec_block_probe_test PRIVATE ${SRC})
target_link_libraries(fec_block_probe_test GTest::gtest_main)
gtest_discover_tests(fec_block_probe_test)

add_executable(rtp_hole_probe_test RtpHoleProbe_test.cpp)
target_include_directories(rtp_hole_probe_test PRIVATE ${SRC})
target_link_libraries(rtp_hole_probe_test GTest::gtest_main)
gtest_discover_tests(rtp_hole_probe_test)

add_executable(release_probe_test ReleaseProbe_test.cpp)
target_include_directories(release_probe_test PRIVATE ${SRC})
target_link_libraries(release_probe_test GTest::gtest_main)
gtest_discover_tests(release_probe_test)

# wfb-ng's real rx Aggregator (rx.cpp built as in the app: shared-library mode, wfb_log.h preinclude) fed by our
# Transmitter: the front-block drain (docs/xr/fec-block-probe.md §8). Needs libpcap (rx.cpp's Receiver).
pkg_check_modules(pcap REQUIRED IMPORTED_TARGET libpcap)
add_executable(rx_drain_test
    RxDrain_test.cpp
    rx_replay.cpp
    ${SRC}/TxFrame.cpp
    ${SRC}/wfb-ng/src/rx.cpp
    ${SRC}/wfb-ng/src/radiotap.c
    ${SRC}/wfb-ng/src/wifibroadcast.cpp
    ${SRC}/wfb-ng/src/zfex.c)
set_source_files_properties(rx_replay.cpp ${SRC}/wfb-ng/src/rx.cpp PROPERTIES
    COMPILE_DEFINITIONS "__WFB_RX_SHARED_LIBRARY__;PREINCLUDE_FILE=<${SRC}/wfb_log.h>")
target_include_directories(rx_drain_test PRIVATE ${LOG_SHIM} ${CMAKE_CURRENT_SOURCE_DIR}/host_shim ${SRC} ${SRC}/wfb-ng ${SRC}/devourer)
target_link_libraries(rx_drain_test PkgConfig::sodium PkgConfig::pcap GTest::gtest_main pthread)
gtest_discover_tests(rx_drain_test)

# The pre-flight channel survey's app side on devourer's chanmig library (docs/xr/channel-survey-design.md, phase 1).
add_executable(channel_survey_test ChannelSurvey_test.cpp SurveyRunner_test.cpp ${SRC}/devourer/src/chanmig/ChannelScore.cpp)
target_include_directories(channel_survey_test PRIVATE ${SRC} ${SRC}/devourer/src)
target_link_libraries(channel_survey_test GTest::gtest_main pthread)
gtest_discover_tests(channel_survey_test)
