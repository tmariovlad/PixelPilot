package com.openipc.xr;

import static org.junit.Assert.*;
import org.junit.Test;

public class PhaseMeterTest {
    private static final long P = 8_333_333L;      // 120 Hz
    private static final long LATCH = 1_000_000_000L;
    private static final double EPS_NS = 20_000;   // 20 us

    private static long[] framesAt(long... readyNs) { return readyNs; }

    @Test public void framesOneMsBeforeTheLatchWaitOneMs() {
        long[] t = framesAt(LATCH - 1_000_000, LATCH + P - 1_000_000, LATCH + 2 * P - 1_000_000);
        PhaseMeter.Result r = PhaseMeter.measure(t, t.length, LATCH, P);
        assertEquals(3, r.n);
        assertEquals(1_000_000, r.meanWaitNs, EPS_NS);
        assertEquals(1.0, r.concentration, 1e-9);
    }

    @Test public void frameJustAfterALatchWaitsAlmostAFullPeriod() {
        long[] t = framesAt(LATCH + 100_000);
        assertEquals(P - 100_000, PhaseMeter.measure(t, 1, LATCH, P).meanWaitNs, EPS_NS);
    }

    @Test public void latchReferenceMayLieAfterTheFrames() {
        long[] t = framesAt(LATCH - 10 * P - 2_000_000);
        assertEquals(2_000_000, PhaseMeter.measure(t, 1, LATCH, P).meanWaitNs, EPS_NS);
    }

    // Waits of 0.1 ms and P-0.1 ms straddle the latch: their circular mean is ~0 (or ~P), not P/2.
    @Test public void meanWrapsAroundTheLatch() {
        long[] t = framesAt(LATCH - 100_000, LATCH + 100_000);
        double w = PhaseMeter.measure(t, 2, LATCH, P).meanWaitNs;
        assertTrue("mean " + w, w < 50_000 || w > P - 50_000);
    }

    @Test public void uniformPhasesHaveNoConcentration() {
        int n = 64;
        long[] t = new long[n];
        for (int i = 0; i < n; i++) t[i] = LATCH + i * P + i * (P / n);
        assertEquals(0.0, PhaseMeter.measure(t, n, LATCH, P).concentration, 1e-4);  // P/n truncates to whole ns
    }

    @Test public void onlyTheFirstCountSamplesAreUsed() {
        long[] t = framesAt(LATCH - 1_000_000, LATCH + 4_000_000);
        assertEquals(1, PhaseMeter.measure(t, 1, LATCH, P).n);
        assertEquals(1_000_000, PhaseMeter.measure(t, 1, LATCH, P).meanWaitNs, EPS_NS);
    }

    @Test public void noSamplesOrNoGridGiveAnEmptyResult() {
        assertEquals(0, PhaseMeter.measure(new long[0], 0, LATCH, P).n);
        assertEquals(0, PhaseMeter.measure(framesAt(LATCH), 1, LATCH, 0).n);
    }
}
