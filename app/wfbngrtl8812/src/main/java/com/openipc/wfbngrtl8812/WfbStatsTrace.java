package com.openipc.wfbngrtl8812;

import android.os.Build;
import android.os.Trace;

/**
 * Writes each wfb-ng stats interval (one native poll, ~300 ms) as system-trace counters, so a Perfetto trace of the
 * app carries the link state next to the per-packet RTP marks: packets received over the air (data + FEC parity),
 * packets repaired by FEC, packets still lost after FEC, decryption errors, the mapped RSSI and the raw RSSI / SNR of
 * each receive chain (so a trace shows which Quest antenna carries the signal). Used by the in-trace
 * A/B analyses (scripts/quest-latch). No cost unless a trace is recording.
 */
public final class WfbStatsTrace {
    /** Where counters go; the system trace in the app, a map in tests. */
    public interface CounterSink {
        void set(String name, long value);
    }

    private static final CounterSink SYSTEM_TRACE = (name, value) -> {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && Trace.isEnabled()) {
            Trace.setCounter(name, value);
        }
    };

    private WfbStatsTrace() {}

    public static void emit(WfbNGStats s) {
        emit(s, SYSTEM_TRACE);
    }

    static void emit(WfbNGStats s, CounterSink sink) {
        sink.set("ppxr_wfb_p_all", s.count_p_all);
        sink.set("ppxr_wfb_dec_err", s.count_p_dec_err);
        sink.set("ppxr_wfb_fec_rec", s.count_p_fec_recovered);
        sink.set("ppxr_wfb_lost", s.count_p_lost);
        sink.set("ppxr_wfb_rssi", s.avg_rssi);
        sink.set("ppxr_wfb_rssi_a", s.rssi_a);
        sink.set("ppxr_wfb_rssi_b", s.rssi_b);
        sink.set("ppxr_wfb_snr_a", s.snr_a);
        sink.set("ppxr_wfb_snr_b", s.snr_b);
    }
}
