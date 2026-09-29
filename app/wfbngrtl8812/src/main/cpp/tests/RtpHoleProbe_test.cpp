#include "LineRateLimiter.h"
#include "RtpHoleProbe.h"
#include "WfbPktLostTap.h"

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

// A minimal RTP packet (RFC 3550 fixed header, version 2) as the video aggregator delivers it.
std::vector<uint8_t> rtp(uint16_t seq, uint32_t ssrc = 0x11223344)
{
    std::vector<uint8_t> p(20, 0);
    p[0] = 0x80;
    p[1] = 96;
    p[2] = static_cast<uint8_t>(seq >> 8);
    p[3] = static_cast<uint8_t>(seq);
    p[8] = static_cast<uint8_t>(ssrc >> 24);
    p[9] = static_cast<uint8_t>(ssrc >> 16);
    p[10] = static_cast<uint8_t>(ssrc >> 8);
    p[11] = static_cast<uint8_t>(ssrc);
    return p;
}

std::string deliver(RtpHoleProbe& p, int64_t t, uint16_t seq, uint32_t ssrc = 0x11223344)
{
    const auto pkt = rtp(seq, ssrc);
    return p.onDelivered(t, pkt.data(), pkt.size());
}
}  // namespace

// ---- LineRateLimiter: the per-second line budget shared by the PPXR_FECBLK and PPXR_RTPHOLE probes --------------

TEST(LineRateLimiter, AdmitsTheBudgetPerSecondAndReportsTheRestInTheNextSecond)
{
    LineRateLimiter lim(3);
    int admitted = 0;
    for (int i = 0; i < 5; ++i) admitted += lim.admit(i * MS) ? 1 : 0;
    EXPECT_EQ(admitted, 3);
    EXPECT_EQ(lim.takeSuppressedSuffix(), "");       // none suppressed before this second ended
    ASSERT_TRUE(lim.admit(1'000 * MS));
    EXPECT_EQ(lim.takeSuppressedSuffix(), " suppressed=2");
    EXPECT_EQ(lim.takeSuppressedSuffix(), "");       // reported once
}

// ---- WfbPktLostTap: wfb-ng's "PKT_LOST\t<n>" (rx.cpp send_packet, the data slots skipped before this delivery) ---

TEST(WfbPktLostTap, ParsesAndAccumulatesUntilTaken)
{
    int n = 0;
    EXPECT_TRUE(WfbPktLostTap::parse("PKT_LOST\t3", n));
    EXPECT_EQ(n, 3);
    EXPECT_FALSE(WfbPktLostTap::parse("1790640000123\tSESSION\t1:1:4:8\n", n));
    WfbPktLostTap::clear();
    WfbPktLostTap::observe("PKT_LOST\t2");
    WfbPktLostTap::observe("1790640000123\tSESSION\t1:1:4:8\n");
    WfbPktLostTap::observe("PKT_LOST\t5");
    EXPECT_EQ(WfbPktLostTap::take(), 7);
    EXPECT_EQ(WfbPktLostTap::take(), 0);
    WfbPktLostTap::observe("PKT_LOST\t4");    // e.g. from another channel's aggregator on the same thread
    WfbPktLostTap::clear();
    EXPECT_EQ(WfbPktLostTap::take(), 0);
}

// ---- RtpHoleProbe: one PPXR_RTPHOLE line per hole in the delivered RTP sequence, with the wfb slots lost there ---

TEST(RtpHoleProbe, AContiguousStreamWritesNothing)
{
    RtpHoleProbe p;
    for (uint16_t s = 100; s < 200; ++s) EXPECT_EQ(deliver(p, s * MS, s), "");
}

TEST(RtpHoleProbe, AHoleWithContiguousWfbSlotsHasZeroSlotsLost)
{
    RtpHoleProbe p;
    deliver(p, 1 * MS, 10);
    const std::string l = deliver(p, 2 * MS, 13);   // 11, 12 missing, wfb delivered its slots back to back
    EXPECT_TRUE(has(l, "t_mono_ms=2 ")) << l;
    EXPECT_TRUE(has(l, " rtp_prev=10 rtp_next=13 gap=2 slots_lost=0 session=0")) << l;
}

TEST(RtpHoleProbe, SlotsLostBeforeTheDeliveryGoIntoTheLine)
{
    RtpHoleProbe p;
    deliver(p, 1 * MS, 10);
    p.onSlotsLost(1);
    p.onSlotsLost(2);
    const std::string l = deliver(p, 2 * MS, 14);
    EXPECT_TRUE(has(l, " gap=3 slots_lost=3 ")) << l;
}

TEST(RtpHoleProbe, SlotsLostWithoutAnRtpHoleAreNotCarriedToTheNextHole)
{
    RtpHoleProbe p;
    deliver(p, 1 * MS, 10);
    p.onSlotsLost(2);                               // e.g. FEC-only padding slots that were lost
    EXPECT_EQ(deliver(p, 2 * MS, 11), "");
    const std::string l = deliver(p, 3 * MS, 13);
    EXPECT_TRUE(has(l, " gap=1 slots_lost=0 ")) << l;
}

TEST(RtpHoleProbe, TheSequenceWrapsAt65536)
{
    RtpHoleProbe p;
    deliver(p, 1 * MS, 65534);
    const std::string l = deliver(p, 2 * MS, 1);    // 65535, 0 missing
    EXPECT_TRUE(has(l, " rtp_prev=65534 rtp_next=1 gap=2 ")) << l;
}

TEST(RtpHoleProbe, DuplicatesBackwardJumpsAndBigJumpsResyncWithoutALine)
{
    RtpHoleProbe p;
    deliver(p, 1 * MS, 500);
    EXPECT_EQ(deliver(p, 2 * MS, 500), "");         // duplicate
    EXPECT_EQ(deliver(p, 3 * MS, 400), "");         // backward: a restarted sender
    EXPECT_EQ(deliver(p, 4 * MS, 401), "");         // continues from the new position
    EXPECT_EQ(deliver(p, 5 * MS, 401 + RtpHoleProbe::kMaxGap + 2), "");   // too far to be a hole
    EXPECT_EQ(deliver(p, 6 * MS, 401 + RtpHoleProbe::kMaxGap + 3), "");
}

TEST(RtpHoleProbe, ANewSsrcResyncsWithoutALine)
{
    RtpHoleProbe p;
    deliver(p, 1 * MS, 10, 0xAAAA);
    EXPECT_EQ(deliver(p, 2 * MS, 20, 0xBBBB), "");
    EXPECT_NE(deliver(p, 3 * MS, 22, 0xBBBB), "");
}

TEST(RtpHoleProbe, NonRtpPayloadsAreIgnoredAndTheirSlotLossCarriesOver)
{
    RtpHoleProbe p;
    deliver(p, 1 * MS, 10);
    p.onSlotsLost(1);
    const uint8_t junk[20] = {0x00};
    EXPECT_EQ(p.onDelivered(2 * MS, junk, sizeof(junk)), "");
    const uint8_t runt[4] = {0x80, 96, 0, 11};
    EXPECT_EQ(p.onDelivered(2 * MS, runt, sizeof(runt)), "");
    const std::string l = deliver(p, 3 * MS, 12);
    EXPECT_TRUE(has(l, " gap=1 slots_lost=1 ")) << l;
}

TEST(RtpHoleProbe, AHoleAcrossANewWfbSessionIsFlagged)
{
    RtpHoleProbe p;
    deliver(p, 1 * MS, 10);
    p.onSession();                                  // wfb-ng reset its slot counter: slot loss here is not seen
    const std::string l = deliver(p, 2 * MS, 15);
    EXPECT_TRUE(has(l, " session=1")) << l;
    const std::string next = deliver(p, 3 * MS, 17);
    EXPECT_TRUE(has(next, " session=0")) << next;
}

TEST(RtpHoleProbe, AtMostTenLinesPerSecondAndTheRestIsCounted)
{
    RtpHoleProbe p;
    int lines = 0;
    uint16_t s = 0;
    deliver(p, 0, s);
    for (int i = 0; i < 25; ++i)
    {
        s += 2;
        if (!deliver(p, i * MS, s).empty()) ++lines;
    }
    EXPECT_EQ(lines, RtpHoleProbe::kMaxLinesPerSecond);
    s += 2;
    const std::string l = deliver(p, 1'000 * MS, s);
    EXPECT_TRUE(has(l, " suppressed=15")) << l;
}
