package com.openipc.pixelpilot.stats;

import static org.junit.Assert.*;

import org.junit.Test;

/** The same vectors as scripts/quest-latch/test_owd.py RunningMin (owd.relative): one algorithm, offline and live. */
public class RunningMinTest {
    private static final long MS = 1_000_000L;   // the vectors are in ns

    private static double[] run(long[] t, double[] v, long windowNs) {
        RunningMin m = new RunningMin(windowNs);
        double[] out = new double[t.length];
        for (int i = 0; i < t.length; i++) out[i] = m.add(t[i], v[i]);
        return out;
    }

    @Test public void valueMinusTheTrailingMinimum() {
        double[] out = run(new long[]{0, MS, 2 * MS, 3 * MS, 4 * MS}, new double[]{5.0, 3.0, 4.0, 9.0, 6.0}, 2 * MS);
        assertArrayEquals(new double[]{0.0, 0.0, 1.0, 5.0, 0.0}, out, 0.0);   // at 3 ms the 3.0 at 1 ms has left
    }

    @Test public void anOldMinimumLeavesTheWindow() {
        double[] out = run(new long[]{0, 10 * MS, 20 * MS}, new double[]{1.0, 5.0, 6.0}, 15 * MS);
        assertArrayEquals(new double[]{0.0, 4.0, 1.0}, out, 0.0);             // at 20 ms the 1.0 at 0 ms has left
    }
}
