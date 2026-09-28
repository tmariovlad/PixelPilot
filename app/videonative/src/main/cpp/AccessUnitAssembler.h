#ifndef PIXELPILOT_ACCESSUNITASSEMBLER_H
#define PIXELPILOT_ACCESSUNITASSEMBLER_H

#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include "RtpTag.h"

// What the assembler needs to know about one Annex-B NALU (start code included).
struct NaluInfo
{
    const uint8_t*                        data         = nullptr;
    size_t                                size         = 0;
    bool                                  isVcl        = false;
    bool                                  isConfig     = false;
    bool                                  isAud        = false;
    bool                                  isFirstSlice = false;
    bool                                  endOfAu      = false;  // RTP marker of the packet that completed it
    std::chrono::steady_clock::time_point creationTime{};
    RtpTag                                tag{};  // RTP identity, for the Stats page (RtpTag.h)
};

// Pure bit-level helpers, no allocation, host-testable.
namespace au
{
inline size_t startCodeSize(const uint8_t* d, size_t n)
{
    if (n >= 4 && d[0] == 0 && d[1] == 0 && d[2] == 0 && d[3] == 1) return 4;
    if (n >= 3 && d[0] == 0 && d[1] == 0 && d[2] == 1) return 3;
    return 0;
}

inline int nalType(const uint8_t* d, size_t n, bool h265)
{
    const size_t sc = startCodeSize(d, n);
    if (sc == 0 || n <= sc) return -1;
    return h265 ? (d[sc] & 0x7E) >> 1 : d[sc] & 0x1F;
}

// First slice of a new picture: H.264 first_mb_in_slice == 0 (ue(v) coded as a single '1' bit),
// H.265 first_slice_segment_in_pic_flag. Both are the MSB of the first byte after the NAL header.
inline bool isFirstSliceOfPicture(const uint8_t* d, size_t n, bool h265)
{
    const size_t sc  = startCodeSize(d, n);
    const size_t hdr = h265 ? 2 : 1;
    if (sc == 0 || n <= sc + hdr) return false;
    return (d[sc + hdr] & 0x80) != 0;
}

inline NaluInfo classify(const uint8_t*                        d,
                         size_t                                n,
                         bool                                  h265,
                         bool                                  endOfAu,
                         std::chrono::steady_clock::time_point t,
                         const RtpTag&                         tag = RtpTag{})
{
    NaluInfo i;
    i.data         = d;
    i.size         = n;
    i.endOfAu      = endOfAu;
    i.creationTime = t;
    i.tag          = tag;
    const int type = nalType(d, n, h265);
    if (h265)
    {
        i.isVcl    = type >= 0 && type <= 31;
        i.isConfig = type == 32 || type == 33 || type == 34;  // VPS, SPS, PPS
        i.isAud    = type == 35;
    }
    else
    {
        i.isVcl    = type >= 1 && type <= 5;
        i.isConfig = type == 7 || type == 8;  // SPS, PPS
        i.isAud    = type == 9;
    }
    i.isFirstSlice = i.isVcl && isFirstSliceOfPicture(d, n, h265);
    return i;
}
}  // namespace au

// Joins the NALUs of one access unit so the decoder receives a whole picture per input buffer
// and never has to wait for the next picture to learn that this one is complete.
// The AU is closed by the RTP marker on its last NALU. If that packet was lost, the AU is
// closed when the next picture visibly starts (AUD, parameter set, or a first slice while a slice
// is already pending), so a lost marker costs one late frame instead of merging two pictures.
class AccessUnitAssembler
{
  public:
    using Emit = std::function<void(
        const uint8_t*                        data,
        size_t                                size,
        std::chrono::steady_clock::time_point firstNaluTime,
        bool                                  isConfig,
        const RtpTag&                         tag)>;  // an AU: the tag of its latest NALU

    // Largest access unit handed to the decoder; the decoder's input buffers are sized to it
    // (max-input-size, DecoderLevers.h) so an assembled picture is never dropped as too big.
    static constexpr size_t kDefaultMaxBytes = 1024 * 1024;

    // How access units were closed. Written by the feeding thread, read by the stats thread.
    struct Stats
    {
        uint64_t closedByMarker        = 0;  // intended path: complete as soon as the last packet arrives
        uint64_t closedByNextPicture   = 0;  // marker missing: the picture waited for the next one
        uint64_t closedBySizeCap       = 0;
        uint64_t passedThroughOversize = 0;
    };

    explicit AccessUnitAssembler(size_t maxBytes = kDefaultMaxBytes) : mMaxBytes(maxBytes) { mBuf.reserve(256 * 1024); }

    void push(const NaluInfo& n, const Emit& emit)
    {
        if (n.isConfig)
        {
            close(emit, mClosedByNextPicture);
            emit(n.data, n.size, n.creationTime, true, n.tag);
            return;
        }
        if (n.isAud || (n.isVcl && n.isFirstSlice && mHasVcl))
        {
            close(emit, mClosedByNextPicture);
        }
        if (mBuf.size() + n.size > mMaxBytes)
        {
            close(emit, mClosedBySizeCap);
        }
        if (n.size > mMaxBytes)
        {
            ++mPassedThroughOversize;
            emit(n.data, n.size, n.creationTime, false, n.tag);
            return;
        }
        if (mBuf.empty())
        {
            mFirstTime = n.creationTime;
        }
        mBuf.insert(mBuf.end(), n.data, n.data + n.size);
        mTag = n.tag;   // closed-by-next-picture happens before this, so the AU keeps its own picture's tag
        mHasVcl = mHasVcl || n.isVcl;
        // The marker may sit on a trailing non-VCL NALU (suffix SEI, filler): close as soon as the
        // AU holds a slice, otherwise the picture would wait for the next one.
        if (n.endOfAu && mHasVcl)
        {
            close(emit, mClosedByMarker);
        }
    }

    Stats stats() const
    {
        Stats s;
        s.closedByMarker        = mClosedByMarker.load(std::memory_order_relaxed);
        s.closedByNextPicture   = mClosedByNextPicture.load(std::memory_order_relaxed);
        s.closedBySizeCap       = mClosedBySizeCap.load(std::memory_order_relaxed);
        s.passedThroughOversize = mPassedThroughOversize.load(std::memory_order_relaxed);
        return s;
    }

    void flush(const Emit& emit)
    {
        if (!mBuf.empty())
        {
            emit(mBuf.data(), mBuf.size(), mFirstTime, false, mTag);
        }
        reset();
    }

    void reset()
    {
        mBuf.clear();
        mHasVcl = false;
    }

    size_t pendingBytes() const { return mBuf.size(); }

  private:
    // Emits the pending AU (if any) and counts why it was closed.
    void close(const Emit& emit, std::atomic<uint64_t>& reason)
    {
        if (mBuf.empty()) return;
        ++reason;
        flush(emit);
    }

    std::atomic<uint64_t> mClosedByMarker{0};
    std::atomic<uint64_t> mClosedByNextPicture{0};
    std::atomic<uint64_t> mClosedBySizeCap{0};
    std::atomic<uint64_t> mPassedThroughOversize{0};

    const size_t                          mMaxBytes;
    std::vector<uint8_t>                  mBuf;
    bool                                  mHasVcl = false;
    std::chrono::steady_clock::time_point mFirstTime{};
    RtpTag                                mTag{};
};

// One line for the stats panel / logs.
inline std::string auStatsSummary(const AccessUnitAssembler::Stats& s)
{
    return "AU marker " + std::to_string(s.closedByMarker) + " next " + std::to_string(s.closedByNextPicture) +
           " cap " + std::to_string(s.closedBySizeCap) + " big " + std::to_string(s.passedThroughOversize);
}

#endif  // PIXELPILOT_ACCESSUNITASSEMBLER_H
