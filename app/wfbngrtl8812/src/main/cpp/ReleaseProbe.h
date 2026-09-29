#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "LineRateLimiter.h"
#include "RtpHeader.h"

// One PPXR_RELEASE line per wfb-ng release call that is not a plain on-arrival delivery, for the -Z (close the FEC
// block at each frame end) analysis (docs/xr/fec-block-probe.md §7, scripts/quest-latch/zflush.py).
//
// Without loss, wfb-ng's Aggregator hands each data fragment out the moment it arrives (src/rx.cpp, the front-block
// loop). A payload waits only behind a gap: it is released later, all at once with the others queued behind it, when
// the block is recovered through FEC (k fragments, which may need the next frame's data or parity sent after it) or
// flushed. One process_packet call = one release. This probe records, per call, the frames it released (RTP timestamp,
// first..last sequence number, whether their marker packet was among them) and the FEC recoveries in it
// (count_p_fec_recovered after minus before; the counter is only reset under the same lock, between calls). A frame
// whose marker packet shares a call with a later frame's packets waited for that next frame.
//
// Written when rec > 0 or n > 1. Line: t_mono_ms=<frame that triggered the call> rec=<fragments recovered> n=<payloads>
// frames=<ts>:<seq first>-<seq last>:<marker 0|1>,... [more=<frames over the cap>] [suppressed=N].
// At most kMaxLinesPerSecond lines per second. Not thread-safe (RX thread, under the link's agg_mutex).
class ReleaseProbe {
  public:
    static constexpr int kMaxLinesPerSecond = 100;
    static constexpr int kMaxFrames = 16;

    void begin(int64_t tNs, uint32_t recoveredCounter) {
        tNs_ = tNs;
        recBefore_ = recoveredCounter;
        n_ = 0;
        more_ = 0;
        frames_.clear();
    }

    void onDelivered(const uint8_t *p, size_t n) {
        ++n_;
        RtpHeader h;
        if (!h.parse(p, n)) return;
        if (!frames_.empty() && frames_.back().ts == h.ts) {
            frames_.back().last = h.seq;
            frames_.back().marker = frames_.back().marker || h.marker;
            return;
        }
        if (static_cast<int>(frames_.size()) >= kMaxFrames) {
            ++more_;
            return;
        }
        frames_.push_back({h.ts, h.seq, h.seq, h.marker});
    }

    // The line for this call, or "" (a plain on-arrival delivery, nothing released, or over budget).
    std::string end(uint32_t recoveredCounter) {
        const uint32_t rec = recoveredCounter >= recBefore_ ? recoveredCounter - recBefore_ : 0;
        if ((rec == 0 && n_ <= 1) || !limiter_.admit(tNs_)) return "";
        std::string line = "t_mono_ms=" + std::to_string(tNs_ / 1'000'000) + " rec=" + std::to_string(rec) +
                           " n=" + std::to_string(n_) + " frames=";
        for (size_t i = 0; i < frames_.size(); ++i) {
            const Frame &f = frames_[i];
            if (i > 0) line += ',';
            line += std::to_string(f.ts) + ':' + std::to_string(f.first) + '-' + std::to_string(f.last) + ':' +
                    (f.marker ? '1' : '0');
        }
        if (more_ > 0) line += " more=" + std::to_string(more_);
        return line + limiter_.takeSuppressedSuffix();
    }

  private:
    struct Frame {
        uint32_t ts;
        uint16_t first, last;
        bool marker;
    };

    int64_t tNs_ = 0;
    uint32_t recBefore_ = 0;
    int n_ = 0;
    int more_ = 0;
    std::vector<Frame> frames_;
    LineRateLimiter limiter_{kMaxLinesPerSecond};
};
