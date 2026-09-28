#include "parser/H26XParser.h"
#include <gtest/gtest.h>
#include <vector>

// A live H.264 <-> H.265 switch (RTP payload 96 <-> 97) must not glue the old codec's half-built NALU to the new
// stream. The old encoder stops mid-frame; if the first new-codec packet that arrives is the end of a fragmented
// NALU (its start was lost), the depacketizer would complete the stale buffer and forward it under the new codec.
namespace {
using Bytes = std::vector<uint8_t>;

struct Out
{
    Bytes nalu;
    bool  h265;
};

Bytes rtp(uint8_t payloadType, uint16_t seq, bool marker, const Bytes& payload)
{
    Bytes p = {0x80, static_cast<uint8_t>((marker ? 0x80 : 0x00) | payloadType), static_cast<uint8_t>(seq >> 8),
               static_cast<uint8_t>(seq & 0xFF), 0, 0, 0, 1, 0, 0, 0, 2};
    p.insert(p.end(), payload.begin(), payload.end());
    return p;
}

struct H26XParserTest : ::testing::Test
{
    std::vector<Out> out;
    H26XParser       parser{[this](const NALU& n)
                      { out.push_back({Bytes(n.getData(), n.getData() + n.getSize()), n.IS_H265_PACKET}); }};
    uint16_t         seq = 500;

    void send(uint8_t pt, bool marker, const Bytes& payload)
    {
        auto p = rtp(pt, seq++, marker, payload);
        parser.parse_rtp_stream(p.data(), p.size());
    }
};

// H.264 FU-A start of a non-IDR slice with nri 2: the rebuilt NAL header is 0x41, which read as H.265 is type 32 (VPS).
const Bytes kH264FuStart = {0x5C, 0x81, 0xAA, 0xBB, 0xCC, 0xDD};
// H.265 FU (type 49) end fragment of a TRAIL_R slice (FU header E=1, type 1).
const Bytes kH265FuEnd = {0x62, 0x01, 0x41, 0x11, 0x22, 0x33, 0x44};
// H.265 single-NALU packet: a VPS (type 32).
const Bytes kH265Vps = {0x40, 0x01, 0x0C, 0x01, 0xFF, 0xFF};
}  // namespace

TEST_F(H26XParserTest, AHalfBuiltNaluOfTheOldCodecIsDroppedOnASwitch)
{
    send(96, false, kH264FuStart);   // the H.264 encoder stops mid-NALU
    seq += 3;                        // the H.265 start fragment is lost
    send(97, true, kH265FuEnd);
    EXPECT_TRUE(out.empty()) << "the stale H.264 bytes were forwarded as an H.265 NALU of size "
                             << (out.empty() ? 0 : out[0].nalu.size());
}

TEST_F(H26XParserTest, TheNewCodecsNalusFlowAfterTheSwitch)
{
    send(96, false, kH264FuStart);
    send(97, true, kH265Vps);
    ASSERT_EQ(1u, out.size());
    EXPECT_TRUE(out[0].h265);
    EXPECT_EQ(Bytes({0, 0, 0, 1, 0x40, 0x01, 0x0C, 0x01, 0xFF, 0xFF}), out[0].nalu);
}

// Within one codec a fragmented NALU is still assembled across packets (the reset happens only on a switch).
TEST_F(H26XParserTest, FragmentsOfOneCodecAreStillAssembled)
{
    send(97, false, {0x62, 0x01, 0x81, 0x01, 0x02});   // FU start, TRAIL_R
    send(97, true, {0x62, 0x01, 0x41, 0x03, 0x04});    // FU end
    ASSERT_EQ(1u, out.size());
    EXPECT_TRUE(out[0].h265);
    EXPECT_EQ(Bytes({0, 0, 0, 1, 0x02, 0x01, 0x01, 0x02, 0x03, 0x04}), out[0].nalu);
}
