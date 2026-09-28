#include "FrameTimeline.h"

#include <gtest/gtest.h>

namespace
{
RtpTag tag(uint32_t ts, int64_t completeNs, uint32_t ssrc = 0xABCD)
{
    return RtpTag{ssrc, ts, completeNs, true};
}
}  // namespace

TEST(FrameTimeline, OneInputPerFrameGivesOneRecord)
{
    FrameTimeline t;
    t.onQueued(1000, tag(9000, 5'000'000));
    t.onDecoded(1000, 6'500'000);
    auto out = t.drain();
    ASSERT_EQ(out.size(), 1u);
    EXPECT_EQ(out[0].ssrc, 0xABCDu);
    EXPECT_EQ(out[0].ts, 9000u);
    EXPECT_EQ(out[0].completeNs, 5'000'000);
    EXPECT_EQ(out[0].decodedNs, 6'500'000);
    EXPECT_TRUE(t.drain().empty());
}

TEST(FrameTimeline, SlicesFedSeparatelyUseTheLastSlicesCompletion)
{
    // Per-NALU feeding: three slices of one frame, three input PTS; MediaCodec returns the first one's PTS.
    FrameTimeline t;
    t.onQueued(1000, tag(9000, 5'000'000));
    t.onQueued(1001, tag(9000, 5'400'000));
    t.onQueued(1002, tag(9000, 5'800'000));
    t.onDecoded(1000, 7'000'000);
    auto out = t.drain();
    ASSERT_EQ(out.size(), 1u);
    EXPECT_EQ(out[0].completeNs, 5'800'000);
}

TEST(FrameTimeline, UnknownPtsIsIgnored)
{
    FrameTimeline t;
    t.onQueued(1000, tag(9000, 1));
    t.onDecoded(4242, 2);
    EXPECT_TRUE(t.drain().empty());
}

TEST(FrameTimeline, UntaggedInputsAreNotTracked)
{
    FrameTimeline t;
    t.onQueued(1000, RtpTag{});   // e.g. a stream that did not come over RTP
    t.onDecoded(1000, 2);
    EXPECT_TRUE(t.drain().empty());
}

TEST(FrameTimeline, ASecondOutputForTheSameFrameIsNotCountedTwice)
{
    FrameTimeline t;
    t.onQueued(1000, tag(9000, 1));
    t.onQueued(1001, tag(9000, 2));
    t.onDecoded(1000, 10);
    t.onDecoded(1001, 11);
    EXPECT_EQ(t.drain().size(), 1u);
}

TEST(FrameTimeline, PendingInputsAreBounded)
{
    FrameTimeline t(4);
    for (int64_t pts = 0; pts < 10; ++pts) t.onQueued(pts, tag(static_cast<uint32_t>(pts), pts));
    t.onDecoded(0, 100);   // evicted long ago
    t.onDecoded(9, 100);   // still pending
    auto out = t.drain();
    ASSERT_EQ(out.size(), 1u);
    EXPECT_EQ(out[0].ts, 9u);
}

TEST(FrameTimeline, DecodedRecordsAreBoundedToo)
{
    FrameTimeline t(4, 3);
    for (int64_t pts = 0; pts < 4; ++pts)
    {
        t.onQueued(pts, tag(static_cast<uint32_t>(pts), pts));
        t.onDecoded(pts, pts + 100);
    }
    auto out = t.drain();   // nobody drained for a while: only the newest 3 are kept
    ASSERT_EQ(out.size(), 3u);
    EXPECT_EQ(out[0].ts, 1u);
}

TEST(FrameTimeline, ResetForgetsPendingInputs)
{
    // A codec switch rebuilds the decoder: PTS queued to the old one never come out.
    FrameTimeline t;
    t.onQueued(1000, tag(9000, 1));
    t.reset();
    t.onDecoded(1000, 2);
    EXPECT_TRUE(t.drain().empty());
}
