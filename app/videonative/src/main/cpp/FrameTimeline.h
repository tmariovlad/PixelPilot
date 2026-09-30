#ifndef PIXELPILOT_FRAMETIMELINE_H
#define PIXELPILOT_FRAMETIMELINE_H

#include <cstddef>
#include <cstdint>
#include <deque>
#include <mutex>
#include <vector>

#include "RtpTag.h"

// One decoded frame, keyed like the air's RTP sidecar by (ssrc, RTP timestamp), for the Stats page's per-segment
// latency (app stats.LatencyWindow).
struct FrameTimes
{
    uint32_t ssrc;
    uint32_t ts;
    int64_t  completeNs;
    int64_t  decodedNs;
    int64_t  firstNs;   // the first packet's arrival (RtpTag::firstNs), earliest over the frame's inputs
};

// Links MediaCodec's output back to the RTP frame it came from. Each input buffer's presentation time (unique per
// queueInputBuffer) is remembered with its RtpTag; MediaCodec returns one input's presentation time with the decoded
// frame. A frame fed as several slices has several inputs: its completion is the latest of them. One producer per
// side (decoder input, decoder output) and one consumer (drain), all under one mutex; both queues are bounded, so an
// idle consumer costs only the newest records.
class FrameTimeline
{
  public:
    explicit FrameTimeline(size_t pendingCapacity = 256, size_t doneCapacity = 512)
        : mPendingCapacity(pendingCapacity), mDoneCapacity(doneCapacity)
    {
    }

    void onQueued(int64_t ptsUs, const RtpTag& tag)
    {
        if (!tag.valid) return;
        std::lock_guard<std::mutex> lock(mMutex);
        if (mPending.size() == mPendingCapacity) mPending.pop_front();
        mPending.push_back({ptsUs, tag});
    }

    void onDecoded(int64_t ptsUs, int64_t decodedNs)
    {
        std::lock_guard<std::mutex> lock(mMutex);
        const Pending* hit = nullptr;
        for (auto it = mPending.rbegin(); it != mPending.rend(); ++it)
            if (it->ptsUs == ptsUs)
            {
                hit = &*it;
                break;
            }
        if (hit == nullptr) return;
        const uint32_t ssrc = hit->tag.ssrc, ts = hit->tag.ts;
        if (mHaveLast && ssrc == mLastSsrc && ts == mLastTs) return;  // a second output of the same frame
        int64_t complete = hit->tag.completeNs, first = hit->tag.firstNs;
        for (const Pending& p : mPending)
        {
            if (p.tag.ssrc != ssrc || p.tag.ts != ts) continue;
            if (p.tag.completeNs > complete) complete = p.tag.completeNs;
            if (p.tag.firstNs != 0 && (first == 0 || p.tag.firstNs < first)) first = p.tag.firstNs;
        }
        if (mDone.size() == mDoneCapacity) mDone.pop_front();
        mDone.push_back({ssrc, ts, complete, decodedNs, first});
        mHaveLast = true;
        mLastSsrc = ssrc;
        mLastTs   = ts;
    }

    // Frames decoded since the previous drain, oldest first.
    std::vector<FrameTimes> drain()
    {
        std::lock_guard<std::mutex> lock(mMutex);
        std::vector<FrameTimes> out(mDone.begin(), mDone.end());
        mDone.clear();
        return out;
    }

    // The decoder was rebuilt (codec switch, recovery): inputs queued to the old one never come out.
    void reset()
    {
        std::lock_guard<std::mutex> lock(mMutex);
        mPending.clear();
        mHaveLast = false;
    }

  private:
    struct Pending
    {
        int64_t ptsUs;
        RtpTag  tag;
    };

    const size_t           mPendingCapacity;
    const size_t           mDoneCapacity;
    std::mutex             mMutex;
    std::deque<Pending>    mPending;
    std::deque<FrameTimes> mDone;
    bool                   mHaveLast = false;
    uint32_t               mLastSsrc = 0;
    uint32_t               mLastTs   = 0;
};

#endif  // PIXELPILOT_FRAMETIMELINE_H
