package com.openipc.pixelpilot.stats;

import java.util.ArrayDeque;

/**
 * Each value minus the minimum over the trailing window (t − window, t], with a monotonic deque: the live twin of
 * scripts/quest-latch/owd.py relative(), tested with the same vectors (RunningMinTest). Times in ns, in order.
 * Not thread-safe.
 */
final class RunningMin {
    private final long windowNs;
    private final ArrayDeque<double[]> dq = new ArrayDeque<>();   // {t, v}, values increasing front to back

    RunningMin(long windowNs) {
        this.windowNs = windowNs;
    }

    double add(long tNs, double v) {
        while (!dq.isEmpty() && dq.peekLast()[1] >= v) dq.pollLast();
        dq.addLast(new double[]{tNs, v});
        while (dq.peekFirst()[0] <= tNs - windowNs) dq.pollFirst();
        return v - dq.peekFirst()[1];
    }
}
