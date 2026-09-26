#ifndef PIXELPILOT_FRAMETIMELOG_H
#define PIXELPILOT_FRAMETIMELOG_H

#include <cstddef>
#include <cstdint>
#include <deque>
#include <mutex>
#include <vector>

// Times (CLOCK_MONOTONIC ns) at which decoded frames were handed to the output surface, for the
// compositor-phase meter (XR mode). One producer (the decoder output thread, ~120/s) and one
// consumer that drains periodically; bounded so an idle consumer costs nothing but the newest frames.
class FrameTimeLog
{
  public:
    explicit FrameTimeLog(size_t capacity = 512) : mCapacity(capacity) {}

    void add(int64_t readyNs)
    {
        std::lock_guard<std::mutex> lock(mMutex);
        if (mTimes.size() == mCapacity) mTimes.pop_front();
        mTimes.push_back(readyNs);
    }

    // Frames added since the previous drain, oldest first.
    std::vector<int64_t> drain()
    {
        std::lock_guard<std::mutex> lock(mMutex);
        std::vector<int64_t> out(mTimes.begin(), mTimes.end());
        mTimes.clear();
        return out;
    }

  private:
    const size_t        mCapacity;
    std::mutex          mMutex;
    std::deque<int64_t> mTimes;
};

#endif  // PIXELPILOT_FRAMETIMELOG_H
