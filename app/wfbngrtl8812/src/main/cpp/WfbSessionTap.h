#pragma once

#include <cstdio>
#include <cstring>

// Catches the FEC k/n of the session a wfb-ng Aggregator has just accepted, without touching the wfb-ng submodule:
// rx.cpp logs every new session as IPC_MSG "<ts>\tSESSION\t<epoch>:<fec_type>:<k>:<n>" (wfb-ng src/rx.cpp,
// Aggregator::process_packet), and this port's IPC_MSG (wfb_log.h) passes each message to observe(). The state is
// per thread and the aggregators run synchronously on the RX thread, so clear() before one Aggregator's
// process_packet and consume() after it return that aggregator's session only (FecBlockProbe, WfbngLink.cpp).
struct WfbSessionTap {
    static bool parse(const char *line, int &k, int &n) {
        const char *p = std::strstr(line, "\tSESSION\t");
        if (p == nullptr) return false;
        unsigned long long epoch = 0;
        unsigned type = 0;
        int kk = 0, nn = 0;
        if (std::sscanf(p + 9, "%llu:%u:%d:%d", &epoch, &type, &kk, &nn) != 4) return false;
        if (kk < 1 || nn < kk) return false;
        k = kk;
        n = nn;
        return true;
    }

    static void observe(const char *line) {
        int k = 0, n = 0;
        if (!parse(line, k, n)) return;
        State &s = state();
        s.k = k;
        s.n = n;
        s.fresh = true;
    }

    static void clear() { state().fresh = false; }

    // k/n seen since the last clear()/consume(), if any.
    static bool consume(int &k, int &n) {
        State &s = state();
        if (!s.fresh) return false;
        k = s.k;
        n = s.n;
        s.fresh = false;
        return true;
    }

  private:
    struct State {
        int k = 0, n = 0;
        bool fresh = false;
    };

    static State &state() {
        static thread_local State s;
        return s;
    }
};
