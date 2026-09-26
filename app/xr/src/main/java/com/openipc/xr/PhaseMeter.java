package com.openipc.xr;

/**
 * Where decoded frames land relative to the compositor's latch grid.
 *
 * The Horizon compositor takes the newest video buffer once per display period, a fixed time before
 * vsync (docs/xr/compositor-phase.md, "Compositor phase, measured"). A frame queued at t waits until the next
 * latch: wait = (latch - t) mod period. Averaged on the circle, because waits just below a period and
 * just above zero are the same phase. Pure function, no Android.
 */
public final class PhaseMeter {
    private PhaseMeter() {}

    public static final class Result {
        /** Frames measured. */
        public final int n;
        /** Circular mean of the wait until the next latch, in [0, period). */
        public final double meanWaitNs;
        /** Mean resultant length: 1 = every frame at the same phase, 0 = phases spread uniformly. */
        public final double concentration;

        Result(int n, double meanWaitNs, double concentration) {
            this.n = n;
            this.meanWaitNs = meanWaitNs;
            this.concentration = concentration;
        }
    }

    /**
     * @param readyNs    frame-ready times (CLOCK_MONOTONIC ns); only the first {@code count} are used
     * @param latchRefNs any latch time on the grid (CLOCK_MONOTONIC ns)
     * @param periodNs   display period; <= 0 means no grid yet
     */
    public static Result measure(long[] readyNs, int count, long latchRefNs, long periodNs) {
        if (count <= 0 || periodNs <= 0) return new Result(0, 0, 0);
        double c = 0, s = 0;
        for (int i = 0; i < count; i++) {
            double angle = 2 * Math.PI * Math.floorMod(latchRefNs - readyNs[i], periodNs) / periodNs;
            c += Math.cos(angle);
            s += Math.sin(angle);
        }
        double mean = Math.atan2(s, c);
        if (mean < 0) mean += 2 * Math.PI;
        return new Result(count, mean / (2 * Math.PI) * periodNs, Math.hypot(c, s) / count);
    }
}
