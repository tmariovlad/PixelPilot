package com.openipc.pixelpilot.stats;

import com.openipc.xr.stats.Segment;

import java.util.ArrayDeque;

/**
 * Queueing delay from the Quest alone (docs/xr/stats-backend.md §7, §7.1, §7.2): per frame, the relative one-way
 * delay v = the first packet's arrival (Quest CLOCK_MONOTONIC) − its RTP timestamp / 90 kHz (the air's capture clock),
 * turned into rel by LiveBase (the port of scripts/quest-latch/owd.py LiveBase: drift learnt and taken out, minimum
 * over a trailing window), twice: over {@link #BASE_WINDOW_S} for reading, and unbounded (since the last reset), which
 * is the one for the air's rate control (a standing queue longer than the window would otherwise be swallowed;
 * pixelpilot-xr-36). No sidecar and no clock sync. Here only what LiveBase does not do: the 32-bit RTP timestamp unwrap,
 * a reset on a new SSRC, and the per-window percentiles. Thread-safe.
 */
public final class OwdWindow {
    /** The trailing window of the reading copy; PPXR_STATS prints it as owdw. */
    static final double BASE_WINDOW_S = 60.0;
    private static final double RTP_TICKS_PER_MS = 90.0;

    /** One snapshot: the queueing delay over the stats window, for the 60 s and the unbounded base, and the drift. */
    public static final class Stats {
        public final Segment windowed, unbounded;
        public final double driftMsPerS;

        Stats(Segment windowed, Segment unbounded, double driftMsPerS) {
            this.windowed = windowed;
            this.unbounded = unbounded;
            this.driftMsPerS = driftMsPerS;
        }
    }

    private final long windowUs;
    private final LiveBase base60 = new LiveBase(BASE_WINDOW_S);
    private final LiveBase baseAll = new LiveBase(Double.POSITIVE_INFINITY);
    private final ArrayDeque<double[]> window = new ArrayDeque<>();   // {arrival us, rel 60 s, rel unbounded}
    private boolean have;
    private long ssrc;
    private long lastTs;
    private double tsUnwrapped;

    public OwdWindow(long windowUs) {
        this.windowUs = windowUs;
    }

    public synchronized void add(QuestFrame q) {
        if (q.firstNs == 0) return;
        if (!have || q.ssrc != ssrc) {
            have = true;
            ssrc = q.ssrc;
            tsUnwrapped = q.rtpTs;
            base60.reset();
            baseAll.reset();
            window.clear();
        } else {
            tsUnwrapped += (int) (q.rtpTs - lastTs);          // signed 32-bit step: a wrap is just the next frame
        }
        lastTs = q.rtpTs;
        double v = q.firstNs / 1e6 - tsUnwrapped / RTP_TICKS_PER_MS;
        window.addLast(new double[]{q.firstNs / 1000.0, base60.push(q.firstNs, v), baseAll.push(q.firstNs, v)});
    }

    /** The queueing delay's p50/p95 over the last windowUs before nowUs. */
    public synchronized Stats snapshot(long nowUs) {
        while (!window.isEmpty() && window.peekFirst()[0] < nowUs - windowUs) window.pollFirst();
        double[] w = new double[window.size()], u = new double[window.size()];
        int i = 0;
        for (double[] s : window) {
            w[i] = s[1];
            u[i++] = s[2];
        }
        return new Stats(Segment.of(w), Segment.of(u), baseAll.drift());
    }
}
