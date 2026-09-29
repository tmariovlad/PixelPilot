#include "FecBlockProbe.h"
#include "WfbSessionTap.h"

#include <gtest/gtest.h>

#include <string>
#include <vector>

namespace
{
constexpr int64_t MS = 1'000'000;

bool has(const std::string& line, const std::string& part)
{
    return line.find(part) != std::string::npos;
}

// Feeds one received video fragment: the frame itself (for the inter-arrival gaps) and the fragment.
std::vector<std::string> frag(FecBlockProbe& p, int64_t t, uint64_t blk, int f, int ra = 74, int rb = 70)
{
    p.onFrame(t);
    return p.onFragment(t, blk, f, ra, rb);
}
}  // namespace

// ---- WfbSessionTap: k/n of the session the video aggregator just accepted (wfb-ng rx.cpp IPC "SESSION") --------

TEST(WfbSessionTap, ParsesTheSessionIpcLine)
{
    int k = 0, n = 0;
    EXPECT_TRUE(WfbSessionTap::parse("1790640000123\tSESSION\t1790000000:1:4:8\n", k, n));
    EXPECT_EQ(k, 4);
    EXPECT_EQ(n, 8);
    EXPECT_FALSE(WfbSessionTap::parse("1790640000123\tPKT\t1:2:3:4\n", k, n));
    EXPECT_FALSE(WfbSessionTap::parse("1790640000123\tSESSION\tgarbage\n", k, n));
}

TEST(WfbSessionTap, TheTapHoldsOnlyWhatWasObservedSinceTheLastClear)
{
    WfbSessionTap::clear();
    int k = 0, n = 0;
    EXPECT_FALSE(WfbSessionTap::consume(k, n));
    WfbSessionTap::observe("1\tPKT\t1:2\n");
    EXPECT_FALSE(WfbSessionTap::consume(k, n));
    WfbSessionTap::observe("1\tSESSION\t9:1:8:12\n");
    EXPECT_TRUE(WfbSessionTap::consume(k, n));
    EXPECT_EQ(k, 8);
    EXPECT_EQ(n, 12);
    EXPECT_FALSE(WfbSessionTap::consume(k, n));   // consumed
}

// ---- FecBlockProbe ------------------------------------------------------------------------------------------------

TEST(FecBlockProbe, NothingBeforeTheSessionGivesKAndN)
{
    FecBlockProbe p;
    EXPECT_TRUE(frag(p, 0, 10, 0).empty());
    EXPECT_TRUE(frag(p, MS, 11, 0).empty());
}

TEST(FecBlockProbe, ACompleteBlockIsNotReported)
{
    FecBlockProbe p;
    p.onFec(4, 8);
    for (int f = 0; f < 4; ++f) EXPECT_TRUE(frag(p, f * 300'000, 10, f).empty());
    for (int f = 0; f < 4; ++f) EXPECT_TRUE(frag(p, 3 * MS + f * 300'000, 11, f).empty());
}

TEST(FecBlockProbe, ABlockFlushedShortOfKIsReportedWithBitmapSpanAndOutage)
{
    FecBlockProbe p;
    p.onFec(4, 8);
    EXPECT_TRUE(frag(p, 0, 10, 0, 74, 70).empty());
    EXPECT_TRUE(frag(p, 300'000, 10, 1, 73, 69).empty());
    // a 4 ms outage: the rest of block 10 never arrives; block 11 starts after it
    EXPECT_TRUE(frag(p, 4'300'000, 11, 0).empty());
    EXPECT_TRUE(frag(p, 4'600'000, 11, 1).empty());
    EXPECT_TRUE(frag(p, 4'900'000, 11, 2).empty());
    auto lines = frag(p, 5'200'000, 11, 3);   // block 11 reaches k: wfb-ng flushes block 10
    ASSERT_EQ(lines.size(), 1u);
    const std::string& l = lines[0];
    EXPECT_TRUE(has(l, "t_mono_ms=5 ")) << l;
    EXPECT_TRUE(has(l, " blk=10 k=4 n=8 got=11000000 ")) << l;
    EXPECT_TRUE(has(l, " span_us=300 ")) << l;
    EXPECT_TRUE(has(l, " gap_max_us=4000 ")) << l;            // the outage after its last fragment
    EXPECT_TRUE(has(l, " frags=0:0:74:70,1:300:73:69 ")) << l;
    EXPECT_TRUE(has(l, " fcs=- ")) << l;                      // keep_corrupted off: bad FCS not visible
    EXPECT_TRUE(has(l, " reason=flush next=11")) << l;
}

TEST(FecBlockProbe, BadFcsFramesAroundTheBlockAreCountedWhenVisible)
{
    FecBlockProbe p;
    p.onFec(4, 8);
    p.setFcsVisible(true);
    p.onBadFcs(-20 * MS);        // too early: outside [first - 10 ms, flush]
    frag(p, 0, 10, 0);
    p.onBadFcs(1 * MS);
    p.onBadFcs(2 * MS);
    frag(p, 4 * MS, 11, 0);
    frag(p, 4 * MS + 1, 11, 1);
    frag(p, 4 * MS + 2, 11, 2);
    auto lines = frag(p, 4 * MS + 3, 11, 3);
    ASSERT_EQ(lines.size(), 1u);
    EXPECT_TRUE(has(lines[0], " fcs=2 ")) << lines[0];
}

TEST(FecBlockProbe, DuplicateFragmentsDoNotCountTowardsK)
{
    FecBlockProbe p;
    p.onFec(4, 8);
    frag(p, 0, 10, 0);
    frag(p, 1, 10, 0);
    frag(p, 2, 10, 0);
    frag(p, 3, 10, 0);   // four copies of fragment 0: still 1 of 4
    frag(p, 10, 11, 0);
    frag(p, 11, 11, 1);
    frag(p, 12, 11, 2);
    auto lines = frag(p, 13, 11, 3);
    ASSERT_EQ(lines.size(), 1u);
    EXPECT_TRUE(has(lines[0], " got=10000000 ")) << lines[0];
}

TEST(FecBlockProbe, ParityCountsTowardsK)
{
    FecBlockProbe p;
    p.onFec(4, 8);
    frag(p, 0, 10, 0);
    frag(p, 1, 10, 5);
    frag(p, 2, 10, 6);
    EXPECT_TRUE(frag(p, 3, 10, 7).empty());   // 1 data + 3 parity = 4: recovered, nothing to report
    for (int f = 0; f < 4; ++f) EXPECT_TRUE(frag(p, 10 + f, 11, f).empty());
}

TEST(FecBlockProbe, BlocksPushedOutOfTheRingAreReported)
{
    FecBlockProbe p;
    p.onFec(4, 8);
    frag(p, 0, 10, 0);   // block 10 never completes, and nothing after it completes either
    std::vector<std::string> lines;
    for (uint64_t b = 11; b <= 10 + FecBlockProbe::kRingBlocks; ++b)
    {
        auto l = frag(p, static_cast<int64_t>(b) * MS, b, 0);
        lines.insert(lines.end(), l.begin(), l.end());
    }
    ASSERT_FALSE(lines.empty());
    EXPECT_TRUE(has(lines[0], " blk=10 ")) << lines[0];
    EXPECT_TRUE(has(lines[0], " reason=ring")) << lines[0];
}

TEST(FecBlockProbe, ANewFecOrASessionRestartForgetsPendingBlocks)
{
    FecBlockProbe p;
    p.onFec(4, 8);
    frag(p, 0, 10, 0);
    p.onFec(4, 6);   // the air switched FEC: a new session, block numbers start again
    for (int f = 0; f < 4; ++f) EXPECT_TRUE(frag(p, MS + f, 0, f).empty());
}

TEST(FecBlockProbe, AtMostTenLinesPerSecondAndTheRestIsCounted)
{
    FecBlockProbe q;
    q.onFec(2, 4);
    std::vector<std::string> lines;
    int64_t t = 0;
    for (uint64_t b = 0; b < 40; b += 2)   // block b gets 1 of 2 fragments; block b+1 completes and flushes it
    {
        frag(q, t++, b, 0);
        frag(q, t++, b + 1, 0);
        auto l = frag(q, t++, b + 1, 1);
        lines.insert(lines.end(), l.begin(), l.end());
    }
    EXPECT_EQ(lines.size(), 10u);   // 20 failures within the same second: only the first 10 are written
    frag(q, 2'000 * MS, 100, 0);
    frag(q, 2'000 * MS + 1, 101, 0);
    auto l = frag(q, 2'000 * MS + 2, 101, 1);   // a new second: its first line carries what was suppressed
    ASSERT_EQ(l.size(), 1u);
    EXPECT_TRUE(has(l[0], " suppressed=10")) << l[0];
}
