#include "StatsWindow.h"

#include <gtest/gtest.h>

// A stand-in with the aggregator's counter names and clear_stats() semantics (wfb-ng/src/rx.hpp).
namespace {
struct FakeAggregator {
    uint32_t count_p_all = 0, count_p_dec_err = 0, count_p_fec_recovered = 0, count_p_lost = 0, count_p_bad = 0,
             count_p_override = 0, count_p_outgoing = 0;
    int clears = 0;
    void clear_stats() {
        count_p_all = count_p_dec_err = count_p_fec_recovered = count_p_lost = count_p_bad = count_p_override =
            count_p_outgoing = 0;
        clears++;
    }
    void receive(uint32_t pkts, uint32_t lost, uint32_t recovered) {
        count_p_all += pkts;
        count_p_outgoing += pkts;
        count_p_lost += lost;
        count_p_fec_recovered += recovered;
    }
};
}  // namespace

TEST(StatsWindow, ReturnsTheWindowAndResetsTheCounters) {
    FakeAggregator agg;
    agg.receive(100, 3, 7);
    StatsWindow w = take_window(agg);
    EXPECT_EQ(100u, w.all);
    EXPECT_EQ(3u, w.lost);
    EXPECT_EQ(7u, w.fec_recovered);
    EXPECT_EQ(100u, w.outgoing);
    EXPECT_EQ(0u, agg.count_p_all);
    EXPECT_EQ(1, agg.clears);
}

// The dead-link case: nothing arrives between two polls. The old code reset the counters only on the next video
// packet, so this second poll repeated all=100, lost=3 forever.
TEST(StatsWindow, AWindowWithoutPacketsIsZero) {
    FakeAggregator agg;
    agg.receive(100, 3, 7);
    take_window(agg);
    StatsWindow dead = take_window(agg);
    EXPECT_EQ(0u, dead.all);
    EXPECT_EQ(0u, dead.lost);
    EXPECT_EQ(0u, dead.fec_recovered);
}

TEST(StatsWindow, CountsOnlyWhatArrivedSinceTheLastPoll) {
    FakeAggregator agg;
    agg.receive(100, 3, 7);
    take_window(agg);
    agg.receive(40, 1, 0);
    StatsWindow w = take_window(agg);
    EXPECT_EQ(40u, w.all);
    EXPECT_EQ(1u, w.lost);
}
