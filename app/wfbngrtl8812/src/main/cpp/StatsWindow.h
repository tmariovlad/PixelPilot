#pragma once

#include <cstdint>

// One reporting window of a wfb-ng aggregator's packet counters.
//
// take_window() reads the counters and resets them in the same step (the caller holds the lock the RX thread uses).
// The counters used to be reset only when the next video packet arrived, so on a dead link every poll repeated the
// last window: the stats panel froze and the adaptive link was fed stale lost/recovered counts (2026-09-27,
// docs/xr/troubleshooting.md). Now a window in which nothing arrived reports zeros.
struct StatsWindow {
    uint32_t all = 0;
    uint32_t dec_err = 0;
    uint32_t fec_recovered = 0;
    uint32_t lost = 0;
    uint32_t bad = 0;
    uint32_t override_ = 0;
    uint32_t outgoing = 0;
};

template <class Aggregator> StatsWindow take_window(Aggregator &agg) {
    StatsWindow w;
    w.all = agg.count_p_all;
    w.dec_err = agg.count_p_dec_err;
    w.fec_recovered = agg.count_p_fec_recovered;
    w.lost = agg.count_p_lost;
    w.bad = agg.count_p_bad;
    w.override_ = agg.count_p_override;
    w.outgoing = agg.count_p_outgoing;
    agg.clear_stats();
    return w;
}
