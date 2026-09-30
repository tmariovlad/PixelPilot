package com.openipc.pixelpilot.stats;

import com.openipc.xr.stats.Segment;
import com.openipc.xr.stats.StatsSnapshot;

import java.util.Locale;

/**
 * One compact "k=v k=v ..." line per snapshot for logcat (tag {@link #TAG}), so a slot records what the Stats page
 * showed; scripts/quest-latch/stats_log.py turns a detached capture into a TSV. The key order below is the only
 * definition of the format: the parser takes whatever keys it finds. Unknown values are "-". t is the Quest's
 * CLOCK_MONOTONIC in ms (the tick time), the same clock as the Perfetto traces.
 */
public final class StatsLine {
    public static final String TAG = "PPXR_STATS";

    private StatsLine() {
    }

    public static String format(StatsSnapshot s, long questMs) {
        StringBuilder b = new StringBuilder(512);
        b.append("t=").append(questMs);
        seg(b, "enc", s.encode);
        seg(b, "snd", s.airSend);
        seg(b, "lnk", s.link);
        seg(b, "dec", s.decode);
        seg(b, "dsp", s.toDisplay);
        seg(b, "tot", s.total);
        kv(b, "n", s.matchedFrames);
        kv(b, "sync", s.clockSynced ? 1 : 0);
        kv(b, "rtt", s.clockRttMs, "%.2f");
        kv(b, "age", s.sidecarAgeMs, "%.0f");
        kv(b, "mcs", s.mcs);
        kv(b, "nss", s.nss);
        kv(b, "bw", s.bwMhz);
        kv(b, "sgi", s.sgi);
        kv(b, "stbc", s.stbc);
        kv(b, "ldpc", s.ldpc);
        kv(b, "share", s.rateSharePct, "%.1f");
        kv(b, "rssiA", s.rssiADbm);
        kv(b, "rssiB", s.rssiBDbm);
        kv(b, "snrA", s.snrADb);
        kv(b, "snrB", s.snrBDb);
        kv(b, "pdata", s.pDataPct, "%.2f");
        kv(b, "post", s.postFecPct, "%.2f");
        kv(b, "fec", s.fecRecPerS, "%.1f");
        kv(b, "holes", s.holesPerS, "%.1f");
        kv(b, "fps", s.fpsDecoded, "%.1f");
        kv(b, "undec", s.undecodedPerS, "%.1f");
        kv(b, "decerr", s.decErr);
        kv(b, "idrok", s.idrReqOkPerS, "%.2f");
        kv(b, "idrfail", s.idrReqFailedPerS, "%.2f");
        kv(b, "frozen", s.frozenSlicesPerS, "%.1f");
        kv(b, "kb", s.frameKbP50, "%.0f");
        kv(b, "pkts", s.pktsPerFrameP50, "%.0f");
        kv(b, "idr", s.idrPerS, "%.2f");
        seg(b, "owd", s.owd);
        kv(b, "owdw", (int) OwdWindow.BASE_WINDOW_S);   // owd50/95: base over the last owdw s
        seg(b, "owdu", s.owdUnbounded);                   // base since the last reset: the rate-control signal
        kv(b, "owdd", s.owdDriftMsPerS, "%.3f");           // learnt air/Quest clock drift, ms per s
        return b.toString();
    }

    private static void seg(StringBuilder b, String name, Segment g) {
        kv(b, name + "50", g.n == 0 ? Double.NaN : g.p50Ms, "%.2f");
        kv(b, name + "95", g.n == 0 ? Double.NaN : g.p95Ms, "%.2f");
    }

    private static void kv(StringBuilder b, String k, double v, String fmt) {
        b.append(' ').append(k).append('=').append(Double.isNaN(v) ? "-" : String.format(Locale.US, fmt, v));
    }

    private static void kv(StringBuilder b, String k, int v) {
        b.append(' ').append(k).append('=').append(v == StatsSnapshot.NA ? "-" : Integer.toString(v));
    }
}
