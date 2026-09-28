package com.openipc.pixelpilot.stats;

import static org.junit.Assert.*;

import org.junit.Test;

/** NTP-style air↔Quest offset from the sidecar's SYNC exchange (t1, t4 on the Quest; t2, t3 on the air). */
public class ClockSyncTest {
    @Test public void noSampleMeansNotSynced() {
        ClockSync c = new ClockSync(8);
        assertFalse(c.synced());
        assertEquals(Long.MIN_VALUE, c.airToQuestUs(123));
    }

    @Test public void symmetricPathGivesTheExactOffset() {
        ClockSync c = new ClockSync(8);
        // air clock = quest clock + 5 s; 1 ms each way; the air turns it around in 10 us
        c.add(1_000_000, 6_001_000, 6_001_010, 1_002_010);
        assertTrue(c.synced());
        assertEquals(5_000_000, c.offsetUs());
        assertEquals(2_000, c.rttUs());
        assertEquals(1_500_000, c.airToQuestUs(6_500_000));
    }

    @Test public void theLowestRttSampleWins() {
        ClockSync c = new ClockSync(8);
        c.add(0, 5_000_000 + 9_000, 5_000_000 + 9_000, 10_000);          // asymmetric: 9 ms out, 1 ms back
        c.add(20_000, 5_020_000 + 500, 5_020_000 + 500, 21_000);          // 0.5 ms each way
        assertEquals(1_000, c.rttUs());
        assertEquals(5_000_000, c.offsetUs());
    }

    @Test public void oldSamplesAgeOutOfTheWindow() {
        ClockSync c = new ClockSync(2);
        c.add(0, 5_000_500, 5_000_500, 1_000);                            // rtt 1 ms, offset 5.0 s
        c.add(10_000, 7_012_000, 7_012_000, 14_000);                      // rtt 4 ms, offset 7.0 s
        c.add(20_000, 7_022_000, 7_022_000, 24_000);                      // rtt 4 ms: the 1 ms sample is gone
        assertEquals(7_000_000, c.offsetUs());
    }

    @Test public void aNegativeRttIsRejected() {
        ClockSync c = new ClockSync(4);
        c.add(1_000, 5_000_000, 5_010_000, 2_000);                        // air turnaround longer than the round trip
        assertFalse(c.synced());
    }
}
