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

// The first RAW arrival of each (ssrc, RTP timestamp), noted by VideoPlayer::onNewRTPData before the reorder queue
// (BufferedPacketQueue). The parser sees a packet only when the queue releases it, so after a loss a frame's first
// packet can wait behind the missing one; its parse-time stamp would then read as a queueing spike right after every
// loss (pixelpilot-xr-36's review, docs/xr/stats-backend.md §7.3). A small ring of the latest frames: a released
// packet is at most a reorder window old. Receive thread only; not thread-safe.
class ArrivalBook
{
  public:
    static constexpr size_t kCapacity = 256;

    void note(uint32_t ssrc, uint32_t ts, int64_t nowNs)
    {
        if (lookup(ssrc, ts) != 0) return;   // a later packet of a frame already seen
        mRing[mNext] = {ssrc, ts, nowNs};
        mNext        = (mNext + 1) % kCapacity;
    }

    // 0 = never seen (or forgotten).
    int64_t lookup(uint32_t ssrc, uint32_t ts) const
    {
        for (size_t k = 1; k <= kCapacity; k++)   // newest first: the usual hit is the current frame
        {
            const Entry& e = mRing[(mNext + kCapacity - k) % kCapacity];
            if (e.ns != 0 && e.ssrc == ssrc && e.ts == ts) return e.ns;
        }
        return 0;
    }

  private:
    struct Entry
    {
        uint32_t ssrc = 0;
        uint32_t ts   = 0;
        int64_t  ns   = 0;
    };
    Entry  mRing[kCapacity]{};
    size_t mNext = 0;
};

inline int64_t rtpTagNowNs()
{
    timespec t{};
    clock_gettime(CLOCK_MONOTONIC, &t);
    return static_cast<int64_t>(t.tv_sec) * 1000000000LL + t.tv_nsec;
}

#endif  // PIXELPILOT_RTPTAG_H
