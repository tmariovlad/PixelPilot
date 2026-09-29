#pragma once

#include <cstddef>
#include <cstdint>

// The RTP fixed header fields the wfb-side probes read from a payload the video aggregator delivers (RFC 3550 §5.1):
// version 2, marker = the last packet of a video frame, 16-bit sequence number, 32-bit timestamp, SSRC.
struct RtpHeader {
    uint16_t seq = 0;
    uint32_t ts = 0;
    uint32_t ssrc = 0;
    bool marker = false;

    // False when the payload is not an RTP v2 packet (too short, or another version).
    bool parse(const uint8_t *p, size_t n) {
        if (n < 12 || (p[0] >> 6) != 2) return false;
        marker = (p[1] & 0x80) != 0;
        seq = static_cast<uint16_t>((p[2] << 8) | p[3]);
        ts = be32(p + 4);
        ssrc = be32(p + 8);
        return true;
    }

  private:
    static uint32_t be32(const uint8_t *p) {
        return (static_cast<uint32_t>(p[0]) << 24) | (static_cast<uint32_t>(p[1]) << 16) |
               (static_cast<uint32_t>(p[2]) << 8) | p[3];
    }
};
