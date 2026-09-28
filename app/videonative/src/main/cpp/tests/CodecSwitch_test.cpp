#include "CodecSwitch.h"
#include <gtest/gtest.h>

// The air unit can switch H.264 <-> H.265 (RTP payload 96 <-> 97) while the app runs. A MediaCodec cannot change its
// MIME type, so the decoder must be rebuilt on the change, and only on the change.

TEST(CodecSwitch, TheFirstNaluIsNotAChange)
{
    CodecSwitch c;
    EXPECT_FALSE(c.changed(false));
    CodecSwitch d;
    EXPECT_FALSE(d.changed(true));
    EXPECT_EQ(0u, d.switches());
}

TEST(CodecSwitch, TheSameCodecIsNeverAChange)
{
    CodecSwitch c;
    for (int i = 0; i < 100; ++i) EXPECT_FALSE(c.changed(true));
    EXPECT_EQ(0u, c.switches());
}

TEST(CodecSwitch, EachSwitchIsReportedOnceOnItsFirstNalu)
{
    CodecSwitch c;
    EXPECT_FALSE(c.changed(false));
    EXPECT_FALSE(c.changed(false));
    EXPECT_TRUE(c.changed(true));    // H.264 -> H.265
    EXPECT_FALSE(c.changed(true));
    EXPECT_FALSE(c.changed(true));
    EXPECT_TRUE(c.changed(false));   // and back
    EXPECT_FALSE(c.changed(false));
    EXPECT_EQ(2u, c.switches());
}

TEST(CodecSwitch, CurrentFollowsTheStream)
{
    CodecSwitch c;
    EXPECT_FALSE(c.known());
    c.changed(true);
    EXPECT_TRUE(c.known());
    EXPECT_TRUE(c.isH265());
    c.changed(false);
    EXPECT_FALSE(c.isH265());
}

TEST(CodecSwitch, SummaryIsEmptyUntilTheFirstSwitch)
{
    CodecSwitch c;
    c.changed(false);
    EXPECT_EQ("", c.summary());
    c.changed(true);
    EXPECT_EQ(" | codec switch 1 (now H.265)", c.summary());
    c.changed(false);
    EXPECT_EQ(" | codec switch 2 (now H.264)", c.summary());
}

// After a reset (e.g. the surface was removed) the next NALU starts fresh: it is not a change, whatever came before.
TEST(CodecSwitch, ResetForgetsTheCodecButKeepsTheCount)
{
    CodecSwitch c;
    c.changed(false);
    c.changed(true);
    c.reset();
    EXPECT_FALSE(c.known());
    EXPECT_FALSE(c.changed(false));
    EXPECT_EQ(1u, c.switches());
}
