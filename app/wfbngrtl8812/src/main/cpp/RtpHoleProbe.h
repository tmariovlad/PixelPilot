#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

#include "LineRateLimiter.h"

// One PPXR_RTPHOLE line per hole in the RTP sequence the video aggregator delivers, with the wfb data slots lost
// between the two packets around it (docs/xr/fec-block-probe.md §6). It splits the missing RTP packets by where they
// were lost: slots_lost = 0 means the neighbours sat in contiguous wfb slots, so the packets never entered wfb_tx on
// the air (air input loss); slots_lost >= gap means they were lost on the radio after FEC. The classes themselves are
// computed offline (scripts/quest-latch/rtp_holes.py), from the raw fields.
//
// Fed on the RX thread from the video aggregator's send_to_socket (every delivered payload, FEC-recovered ones
// included, in wfb slot order) and with wfb-ng's PKT_LOST counts (WfbPktLostTap). A new wfb session resets wfb-ng's
// slot counter, so the slot loss of a hole across it is unknown: session=1. Line:
// t_mono_ms=<Quest CLOCK_MONOTONIC> rtp_prev= rtp_next= gap=<missing RTP packets> slots_lost= session=0|1
// [suppressed=N]. Not thread-safe (RX thread only).
class RtpHoleProbe {
  public:
    static constexpr int kMaxLinesPerSecond = 10;
    static constexpr uint16_t kMaxGap = 1000;   // a forward jump beyond this is a restarted sender, not a hole

    // Data slots wfb-ng skipped before the next delivery (its PKT_LOST).
    void onSlotsLost(int n) { slotsLost_ += n; }

    // A new wfb session (SESSION with a new key): wfb-ng's slot counter restarted.
    void onSession() { session_ = true; }

    // A payload the video aggregator delivered. Returns the PPXR_RTPHOLE line, or "" (no hole, over budget, not RTP).
    std::string onDelivered(int64_t tNs, const uint8_t *p, size_t n) {
        if (n < 12 || (p[0] >> 6) != 2) return "";   // not RTP v2: ignored, its slot loss carries to the next packet
        const uint16_t seq = static_cast<uint16_t>((p[2] << 8) | p[3]);
        const uint32_t ssrc = (static_cast<uint32_t>(p[8]) << 24) | (static_cast<uint32_t>(p[9]) << 16) |
                              (static_cast<uint32_t>(p[10]) << 8) | p[11];
        std::string line;
        if (havePrev_ && ssrc == ssrc_) {
            const uint16_t step = static_cast<uint16_t>(seq - seq_);
            if (step == 0) return "";                 // a duplicate: keep the position and the pending slot loss
            if (step > 1 && step <= kMaxGap + 1 && limiter_.admit(tNs)) {
                line = "t_mono_ms=" + std::to_string(tNs / 1'000'000) + " rtp_prev=" + std::to_string(seq_) +
                       " rtp_next=" + std::to_string(seq) + " gap=" + std::to_string(step - 1) +
                       " slots_lost=" + std::to_string(slotsLost_) + " session=" + (session_ ? "1" : "0") +
                       limiter_.takeSuppressedSuffix();
            }
        }
        havePrev_ = true;
        ssrc_ = ssrc;
        seq_ = seq;
        slotsLost_ = 0;
        session_ = false;
        return line;
    }

  private:
    bool havePrev_ = false;
    uint32_t ssrc_ = 0;
    uint16_t seq_ = 0;
    int slotsLost_ = 0;
    bool session_ = false;
    LineRateLimiter limiter_{kMaxLinesPerSecond};
};
