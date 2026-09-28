#include "RxRateHistogram.h"

#include <gtest/gtest.h>

TEST(RxRateHistogram, EmptyWindowHasNoRate)
{
    RxRateHistogram h;
    RxRateHistogram::Top t = h.take();
    EXPECT_EQ(t.total, 0u);
    EXPECT_EQ(t.packets, 0u);
}

TEST(RxRateHistogram, TheMostFrequentRateAndItsShare)
{
    RxRateHistogram h;
    for (int i = 0; i < 97; ++i) h.add(0x0E, 0, 1, 1, 0);   // HT MCS2, 20 MHz, STBC, LDPC, long GI
    for (int i = 0; i < 3; ++i) h.add(0x0D, 0, 1, 1, 0);    // HT MCS1
    RxRateHistogram::Top t = h.take();
    EXPECT_EQ(t.rateCode, 0x0E);
    EXPECT_EQ(t.bw, 0);
    EXPECT_EQ(t.stbc, 1);
    EXPECT_EQ(t.ldpc, 1);
    EXPECT_EQ(t.sgi, 0);
    EXPECT_EQ(t.packets, 97u);
    EXPECT_EQ(t.total, 100u);
}

TEST(RxRateHistogram, TheSameCodeWithAnotherGiIsAnotherRate)
{
    RxRateHistogram h;
    h.add(0x0E, 0, 1, 1, 0);
    h.add(0x0E, 0, 1, 1, 1);
    h.add(0x0E, 0, 1, 1, 1);
    RxRateHistogram::Top t = h.take();
    EXPECT_EQ(t.sgi, 1);
    EXPECT_EQ(t.packets, 2u);
}

TEST(RxRateHistogram, TakeStartsANewWindow)
{
    RxRateHistogram h;
    h.add(0x0E, 0, 1, 1, 0);
    h.take();
    EXPECT_EQ(h.take().total, 0u);
}

TEST(RxRateHistogram, NineBitRateCodesAreKept)
{
    RxRateHistogram h;
    h.add(0x102, 1, 0, 0, 0);   // halmac VHT code (0x100+)
    EXPECT_EQ(h.take().rateCode, 0x102);
}
