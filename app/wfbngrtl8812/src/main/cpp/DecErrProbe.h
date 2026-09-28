#pragma once

#include <cstdint>
#include <cstdio>
#include <string>

// Where the video aggregator's decrypt errors come from (docs/xr/research/2026-09-27-xr-ux-audit.md, "WRONG KEY after a
// replug"). On 2026-09-28 a whole ~300 ms stats window after an RTL replug had every packet fail to decrypt
// (pkt 145, dec_err 145), with the same session key as before the replug. wfb-ng's own WFB_ERR messages are compiled
// out (wfb_log.h), so nothing said which check failed. This probe attributes each error to the packet type that caused
// it (data vs session) by reading the aggregator's counters around one process_packet call, and reports once per
// second while errors occur, with the time since the link started. Permanent, cheap diagnostics; the caller holds
// agg_mutex, so the 300 ms stats reset (take_window) cannot interleave with one measurement.
class DecErrProbe {
  public:
    // wfb-ng packet types (wifibroadcast.hpp WFB_PACKET_DATA / WFB_PACKET_SESSION)
    static constexpr uint8_t kData = 0x1;
    static constexpr uint8_t kSession = 0x2;
    static constexpr int64_t kReportMs = 1000;

    struct Counters {
        uint32_t dec_err, data, session;
    };

    // The link (re)started: the "since start" clock begins here.
    void start(int64_t now_ms) {
        start_ms_ = now_ms;
        window_ms_ = now_ms;
        reset_window();
    }

    // One packet: its wfb type byte and the aggregator's counters before and after process_packet.
    void record(uint8_t type, const Counters &before, const Counters &after, int64_t now_ms) {
        // after < before only if take_window() reset the counters in between, which agg_mutex rules out; guard anyway
        const uint32_t err = after.dec_err >= before.dec_err ? after.dec_err - before.dec_err : 0;
        if (err) {
            if (type == kData) data_fail_ += err;
            else if (type == kSession) session_fail_ += err;
            else other_fail_ += err;
            if (first_fail_ms_ < 0) first_fail_ms_ = now_ms - start_ms_;
            last_fail_ms_ = now_ms - start_ms_;
        }
        if (after.data > before.data) {
            data_ok_ += after.data - before.data;
            if (first_ok_ms_ < 0) first_ok_ms_ = now_ms - start_ms_;
        }
        if (after.session > before.session) session_ok_ += after.session - before.session;
    }

    // A report line once per kReportMs if this window had decrypt errors; empty otherwise (the window then restarts).
    std::string report(int64_t now_ms) {
        if (now_ms - window_ms_ < kReportMs) return "";
        std::string line;
        if (data_fail_ + session_fail_ + other_fail_ > 0) {
            char buf[256];
            std::snprintf(buf, sizeof buf,
                          "video decrypt errors: data %u session %u other %u | ok: data %u session %u | "
                          "%lld ms after link start (first error %lld, last %lld, first ok data %lld)",
                          data_fail_, session_fail_, other_fail_, data_ok_, session_ok_,
                          static_cast<long long>(now_ms - start_ms_), static_cast<long long>(first_fail_ms_),
                          static_cast<long long>(last_fail_ms_), static_cast<long long>(first_ok_ms_));
            line = buf;
        }
        window_ms_ = now_ms;
        reset_window();
        return line;
    }

  private:
    void reset_window() {
        data_fail_ = session_fail_ = other_fail_ = data_ok_ = session_ok_ = 0;
        first_fail_ms_ = last_fail_ms_ = first_ok_ms_ = -1;
    }

    int64_t start_ms_ = 0;
    int64_t window_ms_ = 0;
    uint32_t data_fail_ = 0, session_fail_ = 0, other_fail_ = 0, data_ok_ = 0, session_ok_ = 0;
    int64_t first_fail_ms_ = -1, last_fail_ms_ = -1, first_ok_ms_ = -1;   // ms after start, -1 = none this window
};
