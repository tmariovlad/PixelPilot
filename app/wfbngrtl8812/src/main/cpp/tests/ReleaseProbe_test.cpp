#include "ReleaseProbe.h"

#include <gtest/gtest.h>

#include <cstdint>
#include <string>
#include <vector>

namespace
{
constexpr int64_t MS = 1'000'000;

bool has(const std::string& line, const std::string& part)
{
    return line.find(part) != std::string::npos;
}

std::vector<uint8_t> rtp(uint16_t seq, uint32_t ts, bool marker)
{
    std::vector<uint8_t> p(20, 0);
    p[0] = 0x80;
    p[1] = static_cast<uint8_t>((marker ? 0x80 : 0) | 96);
    p[2] = static_cast<uint8_t>(seq >> 8);
    p[3] = static_cast<uint8_t>(seq);
    p[4] = static_cast<uint8_t>(ts >> 24);
    p[5] = static_cast<uint8_t>(ts >> 16);
    p[6] = static_cast<uint8_t>(ts >> 8);
    p[7] = static_cast<uint8_t>(ts);
    return p;
}

void deliver(ReleaseProbe& p, uint16_t seq, uint32_t ts, bool marker = false)
{
    const auto pkt = rtp(seq, ts, marker);
    p.onDelivered(pkt.data(), pkt.size());
}
}  // namespace

// ---- ReleaseProbe: one PPXR_RELEASE line per wfb release call that is not a plain on-arrival delivery -----------

TEST(ReleaseProbe, APlainOnArrivalDeliveryWritesNothing)
{
    ReleaseProbe p;
    p.begin(1 * MS, 0);
    deliver(p, 10, 1000);
    EXPECT_EQ(p.end(0), "");
    p.begin(2 * MS, 0);                              // a parity fragment or a duplicate: nothing released
    EXPECT_EQ(p.end(0), "");
}

TEST(ReleaseProbe, ARecoveryListsTheFramesItReleasedWithTheirSeqRangeAndMarker)
{
    ReleaseProbe p;
    p.begin(7 * MS, 40);
    deliver(p, 100, 3000000000u);
    deliver(p, 101, 3000000000u, true);             // frame 3000000000 ends here
    deliver(p, 102, 3000001000u);                   // the next frame's packets, released in the same call
    deliver(p, 103, 3000001000u);
    const std::string l = p.end(41);
    EXPECT_TRUE(has(l, "t_mono_ms=7 rec=1 n=4 frames=3000000000:100-101:1,3000001000:102-103:0")) << l;
}

TEST(ReleaseProbe, SeveralPayloadsWithoutRecoveryAreAHeldRelease)
{
    ReleaseProbe p;
    p.begin(3 * MS, 5);
    deliver(p, 20, 500);
    deliver(p, 21, 500);
    const std::string l = p.end(5);
    EXPECT_TRUE(has(l, " rec=0 n=2 frames=500:20-21:0")) << l;
}

TEST(ReleaseProbe, NonRtpPayloadsAreCountedButNotListed)
{
    ReleaseProbe p;
    p.begin(1 * MS, 0);
    const uint8_t junk[20] = {0};
    p.onDelivered(junk, sizeof(junk));
    deliver(p, 5, 9);
    const std::string l = p.end(1);
    EXPECT_TRUE(has(l, " n=2 frames=9:5-5:0")) << l;
}

TEST(ReleaseProbe, TheFrameListIsCapped)
{
    ReleaseProbe p;
    p.begin(1 * MS, 0);
    for (int i = 0; i < ReleaseProbe::kMaxFrames + 3; ++i) deliver(p, static_cast<uint16_t>(i), static_cast<uint32_t>(i));
    const std::string l = p.end(1);
    EXPECT_TRUE(has(l, " more=3")) << l;
}

TEST(ReleaseProbe, ACounterThatWentBackwardsIsNotARecovery)
{
    ReleaseProbe p;
    p.begin(1 * MS, 10);
    deliver(p, 1, 1);
    EXPECT_EQ(p.end(0), "");                        // stats cleared in between: rec unknown, one payload = on arrival
}

TEST(ReleaseProbe, AtMostTheBudgetPerSecondAndTheRestIsCounted)
{
    ReleaseProbe p;
    int lines = 0;
    for (int i = 0; i < ReleaseProbe::kMaxLinesPerSecond + 7; ++i)
    {
        p.begin(i * MS, 0);
        deliver(p, 1, 1);
        if (!p.end(1).empty()) ++lines;
    }
    EXPECT_EQ(lines, ReleaseProbe::kMaxLinesPerSecond);
    p.begin(1'000 * MS, 0);
    deliver(p, 1, 1);
    EXPECT_TRUE(has(p.end(1), " suppressed=7"));
}
