#include "RxDiag.h"

#include <gtest/gtest.h>

#include <map>
#include <string>

namespace {

devourer::RxRingStats ring(int armed, int min_armed, long long cb_max_us, unsigned long long completions,
                           unsigned long long empties, unsigned long long dropped, unsigned long long resubmit_fail,
                           long long qdepth) {
    devourer::RxRingStats s;
    s.armed = armed;
    s.min_armed = min_armed;
    s.cb_max_us = cb_max_us;
    s.completions = completions;
    s.empties = empties;
    s.dropped = dropped;
    s.resubmit_fail = resubmit_fail;
    s.qdepth = qdepth;
    return s;
}

}  // namespace

TEST(RxDiag, CorruptedFramesAreCountedAndNotForwarded) {
    RxDiag d;
    EXPECT_TRUE(d.on_frame(false, false));   // clean frame: forward
    EXPECT_FALSE(d.on_frame(true, false));   // FCS failed in RF: count, drop
    EXPECT_FALSE(d.on_frame(true, false));
    EXPECT_FALSE(d.on_frame(false, true));   // ICV failed
    EXPECT_FALSE(d.on_frame(true, true));    // both: one CRC, one ICV
    RxDiag::Window w = d.take();
    EXPECT_EQ(3u, w.crc_err);
    EXPECT_EQ(2u, w.icv_err);
    EXPECT_EQ(1u, w.clean);
    w = d.take();                             // the window restarts
    EXPECT_EQ(0u, w.crc_err);
    EXPECT_EQ(0u, w.icv_err);
    EXPECT_EQ(0u, w.clean);
}

TEST(RxDiag, NoRingSnapshotMeansNoRingValues) {
    RxDiag d;
    RxDiag::Window w = d.take();
    EXPECT_FALSE(w.ring_valid);
}

TEST(RxDiag, RingSnapshotsAggregateIntoTheStatsWindow) {
    RxDiag d;
    // Two telemetry windows (e.g. 100 ms each) inside one ~300 ms stats window. Cumulative counters -> deltas,
    // low-water mark -> the minimum, worst consume -> the maximum, backlog -> the maximum.
    d.on_ring(ring(8, 6, 900, 1000, 2, 0, 0, 1));
    d.on_ring(ring(7, 3, 4200, 1600, 9, 4, 1, 5));
    RxDiag::Window w = d.take();
    ASSERT_TRUE(w.ring_valid);
    EXPECT_EQ(1600u, w.completions);          // first take: delta from 0
    EXPECT_EQ(9u, w.empties);
    EXPECT_EQ(4u, w.dropped);
    EXPECT_EQ(1u, w.resubmit_fail);
    EXPECT_EQ(3, w.min_armed);
    EXPECT_EQ(4200, w.cb_max_us);
    EXPECT_EQ(5, w.qdepth_max);

    d.on_ring(ring(8, 8, 150, 2100, 9, 4, 1, 0));
    w = d.take();
    ASSERT_TRUE(w.ring_valid);
    EXPECT_EQ(500u, w.completions);           // delta since the previous take
    EXPECT_EQ(0u, w.empties);
    EXPECT_EQ(0u, w.dropped);
    EXPECT_EQ(0u, w.resubmit_fail);
    EXPECT_EQ(8, w.min_armed);
    EXPECT_EQ(150, w.cb_max_us);
    EXPECT_EQ(0, w.qdepth_max);

    w = d.take();                             // no snapshot since: nothing to report
    EXPECT_FALSE(w.ring_valid);
}

TEST(RxDiag, TraceEmitsOneCounterPerValueAndSkipsRingWhenAbsent) {
    std::map<std::string, long long> got;
    RxDiag::Window w;
    w.crc_err = 7;
    w.icv_err = 1;
    w.clean = 500;
    RxDiag::emit(w, [&](const char *name, long long v) { got[name] = v; });
    EXPECT_EQ(7, got["ppxr_rx_crc_err"]);
    EXPECT_EQ(1, got["ppxr_rx_icv_err"]);
    EXPECT_EQ(500, got["ppxr_rx_clean"]);
    EXPECT_EQ(0u, got.count("ppxr_usb_empties"));   // no ring snapshot in this window

    w.ring_valid = true;
    w.completions = 1600;
    w.empties = 9;
    w.dropped = 4;
    w.resubmit_fail = 1;
    w.min_armed = 3;
    w.cb_max_us = 4200;
    w.qdepth_max = 5;
    got.clear();
    RxDiag::emit(w, [&](const char *name, long long v) { got[name] = v; });
    EXPECT_EQ(1600, got["ppxr_usb_completions"]);
    EXPECT_EQ(9, got["ppxr_usb_empties"]);
    EXPECT_EQ(4, got["ppxr_usb_dropped"]);
    EXPECT_EQ(1, got["ppxr_usb_resubmit_fail"]);
    EXPECT_EQ(3, got["ppxr_usb_min_armed"]);
    EXPECT_EQ(4200, got["ppxr_usb_cb_max_us"]);
    EXPECT_EQ(5, got["ppxr_usb_qdepth"]);
}
