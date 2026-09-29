#pragma once

#include <android/log.h>
#include <cstdarg>
#include <cstdio>

#include "WfbPktLostTap.h"
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

// wfb-ng's IPC messages (IPC_MSG and ANDROID_IPC_MSG) go to logcat as before, and past two taps, without changing the
// wfb-ng submodule: WfbSessionTap picks up the FEC k/n of each new session for FecBlockProbe (PPXR_FECBLK), and
// WfbPktLostTap the post-FEC slot loss ("PKT_LOST") for RtpHoleProbe (PPXR_RTPHOLE).
inline void wfb_ipc_msg(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
inline void wfb_ipc_msg(const char *fmt, ...) {
    char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    __android_log_print(ANDROID_LOG_INFO, "wfb-ng", "%s", buf);
    WfbSessionTap::observe(buf);
    WfbPktLostTap::observe(buf);
}
#define IPC_MSG(...) wfb_ipc_msg(__VA_ARGS__)
#define ANDROID_IPC_MSG(...) wfb_ipc_msg(__VA_ARGS__)
#define IPC_MSG_SEND() (void)0
