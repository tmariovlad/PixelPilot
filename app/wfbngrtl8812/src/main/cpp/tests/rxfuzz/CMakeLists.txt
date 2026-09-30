cmake_minimum_required(VERSION 3.14)
project(RxFuzz LANGUAGES C CXX)
# VARIANTS = a dir with stock/wfb-ng/src and drain/wfb-ng/src (run.sh extracts them with git archive).
if(NOT VARIANTS)
  message(FATAL_ERROR "set -DVARIANTS=<dir with stock/ and drain/> (see run.sh)")
endif()
set(CMAKE_CXX_STANDARD 20)
get_filename_component(SRC ${CMAKE_CURRENT_SOURCE_DIR}/../.. ABSOLUTE)
set(LOG_SHIM ${SRC}/../../../../videonative/src/main/cpp/tests/host_shim)
find_package(PkgConfig REQUIRED)
pkg_check_modules(sodium REQUIRED IMPORTED_TARGET libsodium)
pkg_check_modules(pcap REQUIRED IMPORTED_TARGET libpcap)

# Only rx.cpp / rx.hpp differ between the variants (stock 0da5279, drain 66d4bdb); everything else is the repo's copy.
foreach(V stock drain)
  set(VS ${VARIANTS}/${V})
  # per-variant copies of the two files that include rx.hpp, so each target compiles its own
  configure_file(${SRC}/tests/rx_replay.cpp ${CMAKE_CURRENT_BINARY_DIR}/${V}/rx_replay.cpp COPYONLY)
  add_executable(rx_fuzz_${V}
      rx_fuzz.cpp
      ${CMAKE_CURRENT_BINARY_DIR}/${V}/rx_replay.cpp
      ${VS}/wfb-ng/src/rx.cpp
      ${SRC}/TxFrame.cpp
      ${SRC}/wfb-ng/src/radiotap.c
      ${SRC}/wfb-ng/src/wifibroadcast.cpp
      ${SRC}/wfb-ng/src/zfex.c)
  set_source_files_properties(${CMAKE_CURRENT_BINARY_DIR}/${V}/rx_replay.cpp ${VS}/wfb-ng/src/rx.cpp PROPERTIES
      COMPILE_DEFINITIONS "__WFB_RX_SHARED_LIBRARY__;PREINCLUDE_FILE=<${SRC}/wfb_log.h>"
      INCLUDE_DIRECTORIES "${VS};${SRC}/tests")
  target_include_directories(rx_fuzz_${V} PRIVATE ${LOG_SHIM} ${SRC}/tests/host_shim ${SRC} ${SRC}/wfb-ng ${SRC}/tests ${SRC}/devourer)
  target_link_libraries(rx_fuzz_${V} PkgConfig::sodium PkgConfig::pcap pthread)
endforeach()
