#ifndef PIXELPILOT_RTPTAG_H
#define PIXELPILOT_RTPTAG_H

#include <cstdint>
#include <ctime>

// The RTP identity of a NALU / access unit / decoder input, and when it was complete on the Quest: CLOCK_MONOTONIC
// ns at which its last RTP packet was handed to the parser (after the reorder queue). Carried from the depacketizer
// to the decoder so a decoded frame can be matched to the air's RTP sidecar (FrameTimeline.h, app stats package).
// valid == false: the data did not come over RTP.
struct RtpTag
{
    uint32_t ssrc       = 0;
    uint32_t ts         = 0;
    int64_t  completeNs = 0;
    bool     valid      = false;
};

inline int64_t rtpTagNowNs()
{
    timespec t{};
    clock_gettime(CLOCK_MONOTONIC, &t);
    return static_cast<int64_t>(t.tv_sec) * 1000000000LL + t.tv_nsec;
}

#endif  // PIXELPILOT_RTPTAG_H
