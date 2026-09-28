package com.openipc.xr.stats;

import java.util.Arrays;

/** One latency segment over a window: median and 95th percentile in ms, and how many frames it covers (0 = no data). */
public final class Segment {
    public static final Segment NONE = new Segment(Double.NaN, Double.NaN, 0);

    public final double p50Ms, p95Ms;
    public final int n;

    private Segment(double p50Ms, double p95Ms, int n) {
        this.p50Ms = p50Ms;
        this.p95Ms = p95Ms;
        this.n = n;
    }

    /** Percentiles (linear interpolation) of the non-NaN samples; NONE when there are none. */
    public static Segment of(double[] ms) {
        if (ms == null) return NONE;
        double[] v = Arrays.stream(ms).filter(x -> !Double.isNaN(x)).sorted().toArray();
        if (v.length == 0) return NONE;
        return new Segment(quantile(v, 0.5), quantile(v, 0.95), v.length);
    }

    private static double quantile(double[] sorted, double q) {
        double pos = q * (sorted.length - 1);
        int lo = (int) Math.floor(pos);
        int hi = Math.min(lo + 1, sorted.length - 1);
        return sorted[lo] + (pos - lo) * (sorted[hi] - sorted[lo]);
    }
}
