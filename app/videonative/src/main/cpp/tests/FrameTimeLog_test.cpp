#include "FrameTimeLog.h"
#include <gtest/gtest.h>

TEST(FrameTimeLog, DrainReturnsFramesInOrderThenEmpties)
{
    FrameTimeLog log(8);
    log.add(10);
    log.add(20);
    log.add(30);
    EXPECT_EQ(log.drain(), (std::vector<int64_t>{10, 20, 30}));
    EXPECT_TRUE(log.drain().empty());
}

TEST(FrameTimeLog, KeepsOnlyTheNewestWhenFull)
{
    FrameTimeLog log(3);
    for (int64_t t = 1; t <= 5; ++t) log.add(t);
    EXPECT_EQ(log.drain(), (std::vector<int64_t>{3, 4, 5}));
}

TEST(FrameTimeLog, AddAfterDrainStartsFresh)
{
    FrameTimeLog log(3);
    log.add(1);
    log.drain();
    log.add(2);
    EXPECT_EQ(log.drain(), (std::vector<int64_t>{2}));
}
