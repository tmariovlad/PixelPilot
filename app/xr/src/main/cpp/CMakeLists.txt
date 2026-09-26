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

# Newer-than-minSdk NDK APIs (ATrace_setCounter) are weak and must sit behind __builtin_available.
target_compile_definitions(PixelPilotXr PRIVATE __ANDROID_UNAVAILABLE_SYMBOLS_ARE_WEAK__)
target_compile_options(PixelPilotXr PRIVATE -Werror=unguarded-availability)

target_link_libraries(PixelPilotXr
    OpenXR::headers
    OpenXR::openxr_loader
    android
    log
    EGL
    GLESv3)
