cmake_minimum_required(VERSION 3.22.1)
project(PixelPilotXr CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(OpenXR REQUIRED CONFIG)

add_library(PixelPilotXr SHARED
    EglContext.cpp
    XrLayers.cpp
    XrRuntime.cpp
    xr_jni.cpp)

target_link_libraries(PixelPilotXr
    OpenXR::headers
    OpenXR::openxr_loader
    android
    log
    EGL
    GLESv3)
