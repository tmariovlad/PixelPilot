package com.openipc.pixelpilot.stats;

import com.openipc.xr.stats.Segment;

import java.util.ArrayDeque;

/**
 * Queueing delay from the Quest alone (docs/xr/stats-backend.md §7, §7.1): per frame, the relative one-way delay =
 * the first packet's arrival (Quest CLOCK_MONOTONIC) − its RTP timestamp / 90 kHz (the air's capture clock),
 * detrended by the air/Quest clock drift, minus its running minimum over {@link #BASELINE_NS} (RunningMin, the same
 * algorithm and vectors as scripts/quest-latch/owd.py). The unknown clock offset cancels; no sidecar and no clock sync,
 * so it does not lag behind a congested link as the sidecar's link segment does. It includes the air's encode time,
 * which varies with frame size (openipc-1f). Thread-safe.
 */
public final class OwdWindow {
    /** The base must be older than a standing queue: with 2 / 10 / 60 s, m6b25f46's +55 ms queue read 3.1 / 4.9 /
     * 59.9 ms (pixelpilot-xr-36, §7.1). PPXR_STATS prints it as owdw. */
    static final long BASELINE_NS = 60_000_000_000L;
    /** Air/Quest clock drift, +0.07 ms/s in all 5 captures of 2026-09-30 (§7.1): taken out before the minimum, or a
     * 60 s base would read ~4 ms on a clean link. */
    static final double DRIFT_MS_PER_S = 0.07;
    /** A jump this large between frames is a new RTP timestamp base (waybeam restarted), not a queue: start over. */
    static final double RESET_JUMP_MS = 500.0;
    private static final double RTP_TICKS_PER_MS = 90.0;

    private final long windowUs;
    private final ArrayDeque<double[]> window = new ArrayDeque<>();   // {arrival us, queueing delay ms}
    private RunningMin min;
    private boolean have;
    private long ssrc, lastTs;
    private double tsUnwrapped, lastOwdMs;

    public OwdWindow(long windowUs) {
        this.windowUs = windowUs;
    }

    public synchronized void add(QuestFrame q) {
        if (q.firstNs == 0) return;
        if (!have || q.ssrc != ssrc) {
            restart(q);
        } else {
            tsUnwrapped += (int) (q.rtpTs - lastTs);          // signed 32-bit step: a wrap is just the next frame
            lastTs = q.rtpTs;
        }
        double owd = owdMs(q);
        if (Math.abs(owd - lastOwdMs) > RESET_JUMP_MS) {
            restart(q);
            owd = owdMs(q);
        }
        lastOwdMs = owd;
        double queueing = min.add(q.firstNs, owd - DRIFT_MS_PER_S * (q.firstNs / 1e9));
        window.addLast(new double[]{q.firstNs / 1000.0, queueing});
    }

    private double owdMs(QuestFrame q) {
        return q.firstNs / 1e6 - tsUnwrapped / RTP_TICKS_PER_MS;
    }

    private void restart(QuestFrame q) {
        min = new RunningMin(BASELINE_NS);
        window.clear();
        have = true;
        ssrc = q.ssrc;
        lastTs = q.rtpTs;
        tsUnwrapped = q.rtpTs;
        lastOwdMs = owdMs(q);
    }

    /** p50/p95 of the queueing delay over the last windowUs before nowUs. */
    public synchronized Segment snapshot(long nowUs) {
        while (!window.isEmpty() && window.peekFirst()[0] < nowUs - windowUs) window.pollFirst();
        double[] v = new double[window.size()];
        int i = 0;
        for (double[] s : window) v[i++] = s[1];
        return Segment.of(v);
    }
}
