package com.openipc.pixelpilot.stats;

import java.util.ArrayDeque;

/**
 * Air↔Quest clock offset from the sidecar's SYNC exchange, NTP-style: t1 and t4 on the Quest (CLOCK_MONOTONIC), t2
 * and t3 on the air (CLOCK_MONOTONIC too, see SidecarProtocol). offset = air − Quest = ((t2 − t1) + (t3 − t4)) / 2;
 * its error is at most half the round trip, so the estimate is the offset of the lowest-RTT sample among the last
 * {@code window}. Thread-safe.
 */
public final class ClockSync {
    private final int window;
    private final ArrayDeque<long[]> samples = new ArrayDeque<>();  // {offsetUs, rttUs}

    public ClockSync(int window) {
        this.window = Math.max(1, window);
    }

    public synchronized void add(long t1Us, long t2Us, long t3Us, long t4Us) {
        long rtt = (t4Us - t1Us) - (t3Us - t2Us);
        if (rtt < 0) return;   // impossible on consistent clocks: a garbled or foreign reply
        long offset = ((t2Us - t1Us) + (t3Us - t4Us)) / 2;
        samples.addLast(new long[]{offset, rtt});
        while (samples.size() > window) samples.removeFirst();
    }

    public synchronized boolean synced() {
        return !samples.isEmpty();
    }

    private long[] best() {
        long[] best = null;
        for (long[] s : samples) if (best == null || s[1] < best[1]) best = s;
        return best;
    }

    /** air − Quest in µs; 0 before the first sample. */
    public synchronized long offsetUs() {
        long[] b = best();
        return b == null ? 0 : b[0];
    }

    public synchronized long rttUs() {
        long[] b = best();
        return b == null ? -1 : b[1];
    }

    /** An air timestamp on the Quest's clock, or Long.MIN_VALUE before the first sample. */
    public synchronized long airToQuestUs(long airUs) {
        long[] b = best();
        return b == null ? Long.MIN_VALUE : airUs - b[0];
    }
}
