#include "UplinkSchedule.h"

#include <gtest/gtest.h>

TEST(UplinkSchedule, FirstReportGoesOutAtOnce) {
    UplinkSchedule s;
    EXPECT_TRUE(s.due(0, 250, "aaaa", 0));
}

TEST(UplinkSchedule, NoNewsWaitsForTheInterval) {
    UplinkSchedule s;
    s.sent(1000, 250, "aaaa", 0);
    EXPECT_FALSE(s.due(1000, 250, "aaaa", 0));
    EXPECT_FALSE(s.due(1249, 250, "aaaa", 0));
    EXPECT_TRUE(s.due(1250, 250, "aaaa", 0));
}

TEST(UplinkSchedule, NewIdrRequestGoesOutWithoutWaiting) {
    UplinkSchedule s;
    s.sent(1000, 250, "aaaa", 0);
    EXPECT_TRUE(s.due(1020, 250, "bcde", 0));
    s.sent(1020, 250, "bcde", 0);
    EXPECT_FALSE(s.due(1040, 250, "bcde", 0));
}

TEST(UplinkSchedule, ChangedFecChangeGoesOutWithoutWaiting) {
    UplinkSchedule s;
    s.sent(1000, 250, "aaaa", 0);
    EXPECT_TRUE(s.due(1020, 250, "aaaa", 3));  // raised on loss
    s.sent(1020, 1000, "aaaa", 3);
    EXPECT_TRUE(s.due(2040, 1000, "aaaa", 2));  // decayed: the air unit may lower its FEC now
}

// 4 reports/s with no news: exactly one per 250 ms, polled every kPollMs.
TEST(UplinkSchedule, SteadyRateAtFourPerSecond) {
    UplinkSchedule s;
    int sent = 0;
    for (int64_t t = 0; t < 10000; t += UplinkSchedule::kPollMs) {
        if (s.due(t, 250, "aaaa", 0)) {
            s.sent(t, 250, "aaaa", 0);
            ++sent;
        }
    }
    EXPECT_EQ(40, sent);
}

// A news report restarts the grid: the next timed one comes a full interval later, not at the old slot.
TEST(UplinkSchedule, NewsRestartsTheInterval) {
    UplinkSchedule s;
    s.sent(0, 250, "aaaa", 0);
    s.sent(100, 250, "bcde", 0);
    EXPECT_FALSE(s.due(260, 250, "bcde", 0));
    EXPECT_TRUE(s.due(350, 250, "bcde", 0));
}

// After a long stall (thread starved) there is no burst of catch-up reports.
TEST(UplinkSchedule, NoCatchUpBurstAfterAStall) {
    UplinkSchedule s;
    s.sent(0, 250, "aaaa", 0);
    s.sent(2000, 250, "aaaa", 0);
    EXPECT_FALSE(s.due(2020, 250, "aaaa", 0));
}

TEST(UplinkConfig, SanitizedKeepsWhatWfbAndTheRadioAccept) {
    UplinkConfig c{0, 4, 2, 9};
    UplinkConfig s = c.sanitized();
    EXPECT_EQ(1, s.rate_hz);
    EXPECT_EQ(2, s.fec_n);
    EXPECT_EQ(2, s.fec_k);  // k never above n
    EXPECT_EQ(7, s.mcs);
    EXPECT_EQ(1, (UplinkConfig{-5, 0, 0, -1}.sanitized().fec_k));
    EXPECT_EQ(20, (UplinkConfig{99, 1, 3, 0}.sanitized().rate_hz));
}

TEST(UplinkConfig, IntervalFollowsTheRate) {
    EXPECT_EQ(100, UplinkConfig{}.interval_ms());  // upstream: 10 reports/s
    EXPECT_EQ(250, (UplinkConfig{4, 1, 3, 0}.interval_ms()));
    EXPECT_EQ(1000, (UplinkConfig{0, 1, 3, 0}.interval_ms()));  // clamped to 1/s, never a division by zero
}
