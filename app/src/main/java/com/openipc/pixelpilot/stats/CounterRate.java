package com.openipc.pixelpilot.stats;

import java.util.ArrayDeque;

/** Rate per second of a cumulative counter (e.g. IDR requests sent) over the last {@code windowUs}. Not thread-safe. */
public final class CounterRate {
    private final long windowUs;
    private final ArrayDeque<long[]> samples = new ArrayDeque<>();  // {atUs, value}

    public CounterRate(long windowUs) {
        this.windowUs = windowUs;
    }

    public void add(long atUs, long value) {
        samples.addLast(new long[]{atUs, value});
        while (samples.size() > 1 && samples.peekFirst()[0] < atUs - windowUs) samples.removeFirst();
    }

    /** NaN until two samples span some time. A counter that went backwards (a restart) gives 0, not a negative rate. */
    public double perSecond() {
        if (samples.size() < 2) return Double.NaN;
        long[] first = samples.peekFirst(), last = samples.peekLast();
        long dt = last[0] - first[0];
        if (dt <= 0) return Double.NaN;
        return Math.max(0, last[1] - first[1]) / (dt / 1e6);
    }
}
