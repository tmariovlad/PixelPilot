#ifndef PIXELPILOT_RTPTAG_H
#define PIXELPILOT_RTPTAG_H

#include <cstdint>
#include <ctime>

// The RTP identity of a NALU / access unit / decoder input, and when it was complete on the Quest: CLOCK_MONOTONIC
// ns at which its last RTP packet was handed to the parser (after the reorder queue). Carried from the depacketizer
// to the decoder so a decoded frame can be matched to the air's RTP sidecar (FrameTimeline.h, app stats package).
// valid == false: the data did not come over RTP. firstNs: CLOCK_MONOTONIC ns at which the first packet with this RTP
// timestamp reached the parser (FirstArrival), so a large frame's longer completion does not read as queueing delay
// (docs/xr/stats-backend.md §7).
struct RtpTag
{
    uint32_t ssrc       = 0;
    uint32_t ts         = 0;
    int64_t  completeNs = 0;
    bool     valid      = false;
    int64_t  firstNs    = 0;
};

// The arrival of the first packet of each (ssrc, RTP timestamp): all packets of one frame share its timestamp, so a
// new timestamp or stream starts a new frame. One instance per depacketizer; not thread-safe.
class FirstArrival
{
  public:
    int64_t onPacket(uint32_t ssrc, uint32_t ts, int64_t nowNs)
    {
        if (!mHave || ssrc != mSsrc || ts != mTs)
        {
            mHave    = true;
            mSsrc    = ssrc;
            mTs      = ts;
            mFirstNs = nowNs;
        }
        return mFirstNs;
    }

  private:
    bool     mHave    = false;
    uint32_t mSsrc    = 0;
    uint32_t mTs      = 0;
    int64_t  mFirstNs = 0;
};

inline int64_t rtpTagNowNs()
{
    timespec t{};
    clock_gettime(CLOCK_MONOTONIC, &t);
    return static_cast<int64_t>(t.tv_sec) * 1000000000LL + t.tv_nsec;
}

#endif  // PIXELPILOT_RTPTAG_H
