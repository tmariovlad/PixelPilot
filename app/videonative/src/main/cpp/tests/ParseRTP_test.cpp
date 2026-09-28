#include "parser/ParseRTP.h"
#include <gtest/gtest.h>
#include <vector>

// The RTP marker bit must reach the NALU callback on exactly the NALU its packet completes
// (AccessUnitAssembler relies on it to close an access unit without waiting for the next one).
namespace {
using Bytes = std::vector<uint8_t>;

struct Got
{
    Bytes nalu;
    bool  endOfAu;
};

Bytes rtp(uint16_t seq, bool marker, const Bytes& payload)
{
    Bytes p = {0x80, static_cast<uint8_t>((marker ? 0x80 : 0x00) | 96), static_cast<uint8_t>(seq >> 8),
               static_cast<uint8_t>(seq & 0xFF), 0, 0, 0, 1, 0, 0, 0, 2};
    p.insert(p.end(), payload.begin(), payload.end());
    return p;
}

struct ParseRtpTest : ::testing::Test
{
    std::vector<Got> got;
    RTPDecoder       dec{[this](std::chrono::steady_clock::time_point, const uint8_t* d, int n, bool eau)
                   { got.push_back({Bytes(d, d + n), eau}); }};
    uint16_t         seq = 100;

    void h264(bool marker, const Bytes& payload)
    {
        auto p = rtp(seq++, marker, payload);
        dec.parseRTPH264toNALU(p.data(), p.size());
    }
    void h265(bool marker, const Bytes& payload)
    {
        auto p = rtp(seq++, marker, payload);
        dec.parseRTPH265toNALU(p.data(), p.size());
    }
};
}  // namespace

// A sequence gap is reported once, with the number of packets lost (IdrRequester asks the air for a key frame).
TEST_F(ParseRtpTest, PacketLossIsReportedOncePerGapWithItsSize)
{
    std::vector<int> losses;
    dec.setOnPacketLoss([&](int n) { losses.push_back(n); });
    h264(true, {0x65, 0x88, 0x84, 0x00});
    h264(true, {0x41, 0x9a, 0x00, 0x01});
    EXPECT_TRUE(losses.empty());
    seq += 2;   // packets seq and seq+1 lost
    h264(true, {0x41, 0x9a, 0x00, 0x02});
    h264(true, {0x41, 0x9a, 0x00, 0x03});
    ASSERT_EQ(1u, losses.size());
    EXPECT_EQ(2, losses[0]);
}

TEST_F(ParseRtpTest, H264SingleNaluCarriesMarker)
{
    h264(false, {0x67, 0x42, 0x00, 0x1f});  // SPS, no marker
    h264(true, {0x65, 0x88, 0x84, 0x00});   // IDR slice, marker
    ASSERT_EQ(2u, got.size());
    EXPECT_FALSE(got[0].endOfAu);
    EXPECT_TRUE(got[1].endOfAu);
}

TEST_F(ParseRtpTest, H264FuAMarkerOnlyOnCompletedNalu)
{
    h264(false, {0x7C, 0x85, 0x88, 0x84});  // FU-A start, type 5
    h264(false, {0x7C, 0x05, 0x11, 0x22});  // middle
    EXPECT_TRUE(got.empty());
    h264(true, {0x7C, 0x45, 0x33, 0x44});   // end, marker
    ASSERT_EQ(1u, got.size());
    EXPECT_TRUE(got[0].endOfAu);
    EXPECT_EQ((Bytes{0, 0, 0, 1, 0x65, 0x88, 0x84, 0x11, 0x22, 0x33, 0x44}), got[0].nalu);
}

TEST_F(ParseRtpTest, H265FuMarkerOnlyOnCompletedNalu)
{
    // FU indicator = NAL header with type 49; FU header S/E + type 1 (TRAIL_R)
    h265(false, {0x62, 0x01, 0x81, 0x80, 0x11});  // start
    h265(true, {0x62, 0x01, 0x41, 0x22, 0x33});   // end, marker
    ASSERT_EQ(1u, got.size());
    EXPECT_TRUE(got[0].endOfAu);
}

TEST_F(ParseRtpTest, MarkerIsNotStickyAcrossPackets)
{
    h264(true, {0x61, 0x88, 0x01});   // slice with marker
    h264(false, {0x06, 0x05, 0x01});  // SEI without marker
    ASSERT_EQ(2u, got.size());
    EXPECT_TRUE(got[0].endOfAu);
    EXPECT_FALSE(got[1].endOfAu);
}

// A lost packet inside a fragmented NALU (FU-A). By default the depacketizer drops the whole NALU, so the frame never
// reaches the decoder (2026-09-29: this is where the missing frames at 1080p90 go, docs/xr/link-envelope.md
// "frame fate"). With feed-incomplete-frames on, the NALU is forwarded without the missing bytes.
TEST_F(ParseRtpTest, H264FuAWithMissingFragmentIsDroppedByDefault)
{
    h264(false, {0x7C, 0x85, 0x88, 0x84});  // FU-A start, type 5
    seq++;                                  // the middle fragment is lost
    h264(true, {0x7C, 0x45, 0x33, 0x44});   // end, marker
    EXPECT_TRUE(got.empty());
    h264(false, {0x7C, 0x85, 0x99});         // the next NALU starts clean
    h264(true, {0x7C, 0x45, 0x77});
    ASSERT_EQ(1u, got.size());
    EXPECT_EQ((Bytes{0, 0, 0, 1, 0x65, 0x99, 0x77}), got[0].nalu);
}

TEST_F(ParseRtpTest, H264FuAWithMissingFragmentIsForwardedTruncatedWhenFeedingIncompleteFrames)
{
    dec.setFeedIncompleteFrames(true);
    h264(false, {0x7C, 0x85, 0x88, 0x84});  // FU-A start
    seq++;                                  // lost middle fragment
    h264(true, {0x7C, 0x45, 0x33, 0x44});   // end, marker
    ASSERT_EQ(1u, got.size());
    EXPECT_TRUE(got[0].endOfAu);
    EXPECT_EQ((Bytes{0, 0, 0, 1, 0x65, 0x88, 0x84, 0x33, 0x44}), got[0].nalu);
}
