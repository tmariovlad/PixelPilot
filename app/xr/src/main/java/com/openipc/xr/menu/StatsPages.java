package com.openipc.xr.menu;

import com.openipc.xr.stats.Segment;
import com.openipc.xr.stats.StatsSnapshot;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.function.Supplier;

/**
 * The Stats pages (docs/xr/menu-design.md §6) as text, from the latest {@link StatsSnapshot}: a summary, latency per
 * segment, the link, and the latency levers. Unknown numbers print as "-". The air segments (and the sum) read
 * "n/a (no sidecar)" when the sidecar is older than {@link #SIDECAR_STALE_MS}.
 */
public final class StatsPages implements PageSource {
    public static final String SUMMARY = "stats.summary";
    public static final String LATENCY = "stats.latency";
    public static final String LINK = "stats.link";
    public static final String LEVERS = "stats.levers";
    public static final List<String> PAGES = Collections.unmodifiableList(Arrays.asList(SUMMARY, LATENCY, LINK, LEVERS));
    static final double SIDECAR_STALE_MS = 2000;
    static final String NO_SIDECAR = "n/a (no sidecar)";

    private final Supplier<StatsSnapshot> snapshot;

    public StatsPages(Supplier<StatsSnapshot> snapshot) {
        this.snapshot = snapshot;
    }

    @Override
    public List<String> lines(String pageId) {
        StatsSnapshot s = snapshot.get();
        if (s == null) s = StatsSnapshot.EMPTY;
        switch (pageId) {
            case SUMMARY:
                return summary(s);
            case LATENCY:
                return latency(s);
            case LINK:
                return link(s);
            case LEVERS:
                return levers(s);
            default:
                return Collections.emptyList();
        }
    }

    private static List<String> summary(StatsSnapshot s) {
        String g2g = sidecarFresh(s)
                ? String.format(Locale.US, "G2G est. %s / p95 %s ms (no sensor/panel)", d(s.total.p50Ms, 1),
                        d(s.total.p95Ms, 1))
                : "G2G est. " + NO_SIDECAR;
        return Arrays.asList(g2g,
                String.format(Locale.US, "fps %s  post-FEC %s %%  holes %s/s", d(s.fpsDecoded, 1), d(s.postFecPct, 2),
                        d(s.holesPerS, 1)),
                "RX " + rate(s),
                String.format(Locale.US, "RSSI %s / %s dBm  SNR %s / %s dB", i(s.rssiADbm), i(s.rssiBDbm),
                        i(s.snrADb), i(s.snrBDb)));
    }

    private static List<String> latency(StatsSnapshot s) {
        boolean fresh = sidecarFresh(s);
        List<String> out = new ArrayList<>();
        out.add(segment("capture>encoded", s.encode, fresh));
        out.add(segment("encoded>sent", s.airSend, fresh));
        out.add(segment("sent>complete", s.link, fresh));
        out.add(segment("complete>decoded", s.decode, true));
        out.add(segment("decoded>shown est.", s.toDisplay, true));
        out.add(segment("sum", s.total, fresh));
        out.add(s.clockSynced
                ? String.format(Locale.US, "matched %d frames  clock rtt %s ms", s.matchedFrames, d(s.clockRttMs, 1))
                : String.format(Locale.US, "matched %d frames  clock not synced", s.matchedFrames));
        return out;
    }

    private static List<String> link(StatsSnapshot s) {
        return Arrays.asList(
                "rate " + rate(s),
                String.format(Locale.US, "RSSI A/B  %s / %s dBm", i(s.rssiADbm), i(s.rssiBDbm)),
                String.format(Locale.US, "SNR A/B   %s / %s dB", i(s.snrADb), i(s.snrBDb)),
                String.format(Locale.US, "loss pre-FEC %s %%  post-FEC %s %%", d(s.pDataPct, 1), d(s.postFecPct, 2)),
                String.format(Locale.US, "FEC recovered %s/s  holes %s/s", d(s.fecRecPerS, 0), d(s.holesPerS, 1)));
    }

    private static List<String> levers(StatsSnapshot s) {
        return Arrays.asList(
                String.format(Locale.US, "keyframe requests ok %s/s  failed %s/s", d(s.idrReqOkPerS, 1),
                        d(s.idrReqFailedPerS, 1)),
                String.format(Locale.US, "keyframes sent by the air %s/s", d(s.idrPerS, 1)),
                String.format(Locale.US, "frozen slices %s/s", d(s.frozenSlicesPerS, 1)),
                String.format(Locale.US, "decoded %s fps  undecoded %s/s  errors %s", d(s.fpsDecoded, 1),
                        d(s.undecodedPerS, 1), i(s.decErr)),
                String.format(Locale.US, "frame %s KB p50  %s pkts/frame  air fill %s %%", d(s.frameKbP50, 0),
                        d(s.pktsPerFrameP50, 0), i(s.airFillPct)));
    }

    private static String segment(String name, Segment seg, boolean fresh) {
        String v = !fresh ? NO_SIDECAR
                : seg.n == 0 ? "-" : String.format(Locale.US, "%s / %s ms", d(seg.p50Ms, 1), d(seg.p95Ms, 1));
        return String.format(Locale.US, "%-19s %s", name, v);
    }

    private static String rate(StatsSnapshot s) {
        if (s.mcs == StatsSnapshot.NA) return "-";
        StringBuilder b = new StringBuilder("MCS").append(s.mcs);
        if (s.sgi != StatsSnapshot.NA) b.append(s.sgi == 1 ? " SGI" : " LGI");
        if (s.stbc == 1) b.append(" STBC");
        if (s.ldpc == 1) b.append(" LDPC");
        if (s.nss != StatsSnapshot.NA) b.append(' ').append(s.nss).append("SS");
        if (s.bwMhz != StatsSnapshot.NA) b.append(' ').append(s.bwMhz).append("MHz");
        if (!Double.isNaN(s.rateSharePct)) b.append(String.format(Locale.US, " (%.0f %%)", s.rateSharePct));
        return b.toString();
    }

    private static boolean sidecarFresh(StatsSnapshot s) {
        return !Double.isNaN(s.sidecarAgeMs) && s.sidecarAgeMs <= SIDECAR_STALE_MS;
    }

    private static String d(double v, int decimals) {
        return Double.isNaN(v) ? "-" : String.format(Locale.US, "%." + decimals + "f", v);
    }

    private static String i(int v) {
        return v == StatsSnapshot.NA ? "-" : Integer.toString(v);
    }
}
