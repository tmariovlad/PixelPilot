#ifndef PIXELPILOT_XRINCLUDES_H
#define PIXELPILOT_XRINCLUDES_H

// One place that sets the platform/graphics macros before the OpenXR headers.
#include <EGL/egl.h>
#include <jni.h>
#include <time.h>
#define XR_USE_PLATFORM_ANDROID
#define XR_USE_TIMESPEC
#define XR_USE_GRAPHICS_API_OPENGL_ES
#include <openxr/openxr.h>
#include <openxr/openxr_platform.h>

#endif  // PIXELPILOT_XRINCLUDES_H
