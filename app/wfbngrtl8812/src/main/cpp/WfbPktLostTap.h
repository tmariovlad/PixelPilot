#pragma once

#include <cstdio>
#include <cstring>

// Catches wfb-ng's post-FEC slot loss per delivered packet without touching the wfb-ng submodule: Aggregator::
// send_packet (wfb-ng src/rx.cpp) computes packet_seq = block_idx * k + fragment_idx and, when it jumps, logs
// ANDROID_IPC_MSG "PKT_LOST\t<data slots skipped>" just before handing that packet to send_to_socket. This port routes
// that macro through wfb_log.h, which passes every message to observe(). FEC-only padding slots advance packet_seq too,
// so they are not counted as lost. The count is per thread (all aggregators run on the RX thread): clear() before the
// video aggregator's process_packet, take() in its send_to_socket and after the call (RtpHoleProbe, WfbngLink.cpp).
struct WfbPktLostTap {
    static bool parse(const char *line, int &n) {
        if (std::strncmp(line, "PKT_LOST\t", 9) != 0) return false;
        int v = 0;
        if (std::sscanf(line + 9, "%d", &v) != 1 || v < 0) return false;
        n = v;
        return true;
    }

    static void observe(const char *line) {
        int n = 0;
        if (parse(line, n)) lost() += n;
    }

    static void clear() { lost() = 0; }

    // Slots lost since the last clear()/take().
    static int take() {
        const int n = lost();
        lost() = 0;
        return n;
    }

  private:
    static int &lost() {
        static thread_local int n = 0;
        return n;
    }
};
