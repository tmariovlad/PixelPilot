package com.openipc.xr.stats;

import static org.junit.Assert.*;

import org.junit.Test;

public class StatsSnapshotTest {
    @Test public void emptyMeansNoDataEverywhere() {
        StatsSnapshot s = StatsSnapshot.EMPTY;
        assertEquals(0, s.encode.n);
        assertTrue(Double.isNaN(s.encode.p50Ms));
        assertEquals(0, s.total.n);
        assertEquals(StatsSnapshot.NA, s.rssiADbm);
        assertEquals(StatsSnapshot.NA, s.mcs);
        assertEquals(StatsSnapshot.NA, s.decErr);
        assertTrue(Double.isNaN(s.postFecPct));
        assertTrue(Double.isNaN(s.idrPerS));
        assertFalse(s.clockSynced);
    }

    @Test public void segmentPercentilesOverTheWindow() {
        Segment g = Segment.of(new double[]{5, 1, 4, 2, 3, 10, 6, 7, 8, 9});
        assertEquals(10, g.n);
        assertEquals(5.5, g.p50Ms, 1e-9);      // median of 1..10
        assertEquals(9.55, g.p95Ms, 1e-9);     // linear interpolation at 0.95 * (n - 1)
    }

    @Test public void segmentOfOneValueAndOfNothing() {
        Segment one = Segment.of(new double[]{3.25});
        assertEquals(3.25, one.p50Ms, 0);
        assertEquals(3.25, one.p95Ms, 0);
        assertSame(Segment.NONE, Segment.of(new double[0]));
        assertSame(Segment.NONE, Segment.of(null));
    }

    @Test public void segmentIgnoresNaNSamples() {
        Segment g = Segment.of(new double[]{Double.NaN, 2, Double.NaN, 4});
        assertEquals(2, g.n);
        assertEquals(3, g.p50Ms, 1e-9);
    }

    @Test public void builderSetsWhatItIsGivenAndLeavesTheRestUnknown() {
        StatsSnapshot s = new StatsSnapshot.Builder()
                .encode(Segment.of(new double[]{4}))
                .rate(2, 1, 20, false, true, true, 97.5)
                .rssi(-58, -61)
                .loss(3.9, 0.8, 72.2, 18.9)
                .build();
        assertEquals(4, s.encode.p50Ms, 0);
        assertEquals(2, s.mcs);
        assertEquals(1, s.nss);
        assertEquals(20, s.bwMhz);
        assertEquals(0, s.sgi);
        assertEquals(1, s.stbc);
        assertEquals(97.5, s.rateSharePct, 0);
        assertEquals(-58, s.rssiADbm);
        assertEquals(0.8, s.postFecPct, 0);
        assertEquals(0, s.airSend.n);
        assertEquals(StatsSnapshot.NA, s.snrADb);
        assertTrue(Double.isNaN(s.fpsDecoded));
    }
}
