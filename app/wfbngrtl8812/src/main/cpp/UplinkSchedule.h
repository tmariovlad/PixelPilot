#pragma once

#include <algorithm>
#include <cstdint>
#include <string>

// Airtime of the adaptive-link uplink (GS -> air unit, radio port 160, which also carries the tunnel's uplink).
//
// Upstream sends a link report every 100 ms with FEC 1/5 at MCS0: ~51 frames/s on air, which measurably took airtime
// from the video (fewer video packets per step and a higher pre-FEC loss with the uplink on, docs/xr/link-envelope.md).
// The rate, the FEC and the MCS are now settings; LinkOptions (Java) holds the defaults the app uses and sets them
// before every link start. The values below are only upstream's behaviour, used if nothing is set.
struct UplinkConfig {
    int rate_hz = 10;
    int fec_k = 1;
    int fec_n = 5;
    int mcs = 0;

    // Keeps what wfb-ng and the radio accept: 1 <= k <= n < 256 (tx.cpp CMD_SET_FEC check), HT MCS 0..7 on one
    // stream, and a report rate the air unit's fallback timer can live with.
    UplinkConfig sanitized() const {
        UplinkConfig c = *this;
        c.rate_hz = std::clamp(c.rate_hz, 1, 20);
        c.fec_n = std::clamp(c.fec_n, 1, 255);
        c.fec_k = std::clamp(c.fec_k, 1, c.fec_n);
        c.mcs = std::clamp(c.mcs, 0, 7);
        return c;
    }

    int interval_ms() const { return 1000 / sanitized().rate_hz; }
};

// When the next link report goes out. At a low rate a new IDR request would wait for the next slot, and a lost frame
// then stays broken for that much longer, so a report with news the air unit acts on at once (a new IDR request
// code, a changed fec_change) goes out right away; otherwise one per interval keeps the air unit's fallback timer fed.
class UplinkSchedule {
  public:
    // How often the report loop wakes up to look for news: the worst-case delay of an IDR request (was 100 ms).
    static constexpr int kPollMs = 20;

    bool due(int64_t now_ms, int interval_ms, const std::string &idr_code, int fec_change) const {
        if (!sent_any_) return true;
        if (idr_code != last_idr_code_ || fec_change != last_fec_change_) return true;
        return now_ms - last_sent_ms_ >= interval_ms;
    }

    // A report on the timer keeps its slot grid (the poll wakes up to kPollMs late, which at 250 ms would otherwise
    // stretch the period to 260 ms); a report with news, or one far behind, starts the grid again from now.
    void sent(int64_t now_ms, int interval_ms, const std::string &idr_code, int fec_change) {
        const int64_t since = now_ms - last_sent_ms_;
        const bool on_grid = sent_any_ && since >= interval_ms && since < 2 * interval_ms;
        last_sent_ms_ = on_grid ? last_sent_ms_ + interval_ms : now_ms;
        sent_any_ = true;
        last_idr_code_ = idr_code;
        last_fec_change_ = fec_change;
    }

  private:
    bool sent_any_ = false;
    int64_t last_sent_ms_ = 0;
    std::string last_idr_code_;
    int last_fec_change_ = 0;
};
