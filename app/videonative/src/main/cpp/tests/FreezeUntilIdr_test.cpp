#include "FreezeUntilIdr.h"

#include <gtest/gtest.h>

// After a lost RTP packet, hold the picture on the last good frame: drop every non-key slice until the next key frame
// (or a timeout), so the decoder never shows frames predicted from a missing reference (docs/xr/link-envelope.md).
namespace {
constexpr int H264_P = 1, H264_IDR = 5, H264_SEI = 6, H264_SPS = 7, H264_PPS = 8;
constexpr int H265_TRAIL_R = 1, H265_IDR_W_RADL = 19, H265_CRA = 21, H265_VPS = 32, H265_SPS = 33;
}  // namespace

TEST(FreezeUntilIdr, OffPassesEverythingEvenAfterALoss)
{
    FreezeUntilIdr g;
    g.onLoss(0);
    EXPECT_TRUE(g.admit(H264_P, false, 10));
    EXPECT_FALSE(g.frozen());
    EXPECT_EQ(0u, g.dropped());
}

TEST(FreezeUntilIdr, AfterALossSlicesWaitForTheIdrWhileConfigPasses)
{
    FreezeUntilIdr g;
    g.setEnabled(true);
    EXPECT_TRUE(g.admit(H264_P, false, 0));
    g.onLoss(5);
    EXPECT_TRUE(g.frozen());
    EXPECT_FALSE(g.admit(H264_P, false, 16));
    EXPECT_FALSE(g.admit(H264_P, false, 27));
    EXPECT_TRUE(g.admit(H264_SEI, false, 30));
    EXPECT_TRUE(g.admit(H264_SPS, false, 38));
    EXPECT_TRUE(g.admit(H264_PPS, false, 38));
    EXPECT_TRUE(g.admit(H264_IDR, false, 38));
    EXPECT_FALSE(g.frozen());
    EXPECT_TRUE(g.admit(H264_P, false, 49));
    EXPECT_EQ(2u, g.dropped());
}

TEST(FreezeUntilIdr, ATimeoutResumesWithoutAKeyFrame)
{
    FreezeUntilIdr g(1000);
    g.setEnabled(true);
    g.onLoss(0);
    g.onLoss(500);   // a second loss does not extend the freeze
    EXPECT_FALSE(g.admit(H264_P, false, 999));
    EXPECT_TRUE(g.admit(H264_P, false, 1000));
    EXPECT_FALSE(g.frozen());
}

TEST(FreezeUntilIdr, H265IrapEndsTheFreezeAndTrailingSlicesWait)
{
    FreezeUntilIdr g;
    g.setEnabled(true);
    g.onLoss(0);
    EXPECT_FALSE(g.admit(H265_TRAIL_R, true, 11));
    EXPECT_TRUE(g.admit(H265_VPS, true, 20));
    EXPECT_TRUE(g.admit(H265_SPS, true, 20));
    EXPECT_TRUE(g.admit(H265_IDR_W_RADL, true, 20));
    EXPECT_FALSE(g.frozen());
    g.onLoss(30);
    EXPECT_TRUE(g.admit(H265_CRA, true, 40));
    EXPECT_FALSE(g.frozen());
}

TEST(FreezeUntilIdr, TurningItOffReleasesAFreeze)
{
    FreezeUntilIdr g;
    g.setEnabled(true);
    g.onLoss(0);
    g.setEnabled(false);
    EXPECT_TRUE(g.admit(H264_P, false, 10));
    EXPECT_FALSE(g.frozen());
}
