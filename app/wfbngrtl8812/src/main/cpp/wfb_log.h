#pragma once

#include <android/log.h>
#include <cstdarg>
#include <cstdio>

#include "WfbSessionTap.h"

#define WFB_ERR(...)                                                                                                   \
    do {                                                                                                               \
        __android_log_print(ANDROID_LOG_ERROR, "wfb-ng", __VA_ARGS__);                                                 \
    } while (0)
#define WFB_INFO(...)                                                                                                  \
    do {                                                                                                               \
        (void)0; /*__android_log_print(ANDROID_LOG_INFO, "wfb-ng", __VA_ARGS__);*/                                     \
    } while (0)

#define WFB_DBG(...) (void(0))

#define ANDROID_IPC_MSG(...)                                                                                           \
    do {                                                                                                               \
        __android_log_print(ANDROID_LOG_INFO, "wfb-ng", __VA_ARGS__);                                                  \
    } while (0)

// wfb-ng's IPC messages go to logcat as before, and past WfbSessionTap, which picks up the FEC k/n of each new
// session for FecBlockProbe (PPXR_FECBLK) without changing the wfb-ng submodule.
inline void wfb_ipc_msg(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
inline void wfb_ipc_msg(const char *fmt, ...) {
    char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    __android_log_print(ANDROID_LOG_INFO, "wfb-ng", "%s", buf);
    WfbSessionTap::observe(buf);
}
#define IPC_MSG(...) wfb_ipc_msg(__VA_ARGS__)
#define IPC_MSG_SEND() (void)0
