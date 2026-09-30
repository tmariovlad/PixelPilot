package com.openipc.pixelpilot.stats;

import static org.junit.Assert.*;

import com.openipc.xr.stats.Segment;
import com.openipc.xr.stats.StatsSnapshot;

import java.util.ArrayList;
import java.util.List;

import org.junit.Test;

public class StatsLineTest {
    @Test public void oneLineOfKeyValuePairsInAFixedOrder() {
        StatsSnapshot s = new StatsSnapshot.Builder()
                .encode(Segment.of(new double[]{4.0, 5.0}))
                .matching(12, true, 1.25, 10)
                .rate(2, 1, 20, false, true, true, 97.5)
                .rssi(-58, -61)
                .loss(3.9, 0.8, 72.2, 18.5)
                .owd(Segment.of(new double[]{2.0, 3.0}), Segment.of(new double[]{4.0}), 0.07)
                .build();
        String line = StatsLine.format(s, 123_456_789L);
        assertTrue(line, line.contains(" owd50=2.50 owd95="));
        assertTrue(line, line.contains(" owdw=60 owdu50=4.00 owdu95=4.00 owdd=0.070"));
        assertTrue(line.startsWith("t=123456789 "));
        assertTrue(line.contains(" enc50=4.50 enc95=4.95 "));
        assertTrue(line.contains(" n=12 sync=1 rtt=1.25 "));
        assertTrue(line.contains(" mcs=2 nss=1 bw=20 sgi=0 stbc=1 ldpc=1 share=97.5 "));
        assertTrue(line.contains(" rssiA=-58 rssiB=-61 "));
        assertTrue(line.contains(" pdata=3.90 post=0.80 fec=72.2 holes=18.5 "));
        assertFalse(line.contains("\n"));
    }

    @Test public void unknownValuesAreDashesNotZeros() {
        String line = StatsLine.format(StatsSnapshot.EMPTY, 1);
        assertTrue(line.contains(" enc50=- "));
        assertTrue(line.contains(" mcs=- "));
        assertTrue(line.contains(" sync=0 "));
        for (String kv : line.split(" ")) assertEquals(kv, 2, kv.split("=", -1).length);   // every token is k=v
    }

    @Test public void theKeyOrderIsStable() {
        String a = StatsLine.format(StatsSnapshot.EMPTY, 1);
        String b = StatsLine.format(new StatsSnapshot.Builder().rssi(-40, -41).build(), 2);
        assertEquals(keys(a), keys(b));
    }

    private static List<String> keys(String line) {
        List<String> k = new ArrayList<>();
        for (String kv : line.split(" ")) k.add(kv.substring(0, kv.indexOf('=')));
        return k;
    }

    // --- gating in StatsCollector: a line every 4 ticks (2 s), only while the page is viewed or the pref is on ---

    private static final class NoInputs implements StatsCollector.Inputs {
        @Override public long[] drainFrameTimes() { return null; }
        @Override public long[] leverCounters() { return null; }
        @Override public int[] takeRxRate() { return null; }
        @Override public DisplayEstimate display() { return null; }
    }

    @Test public void noLinesWhileNobodyLooksAndThePrefIsOff() {
        List<String> out = new ArrayList<>();
        StatsCollector c = new StatsCollector(new NoInputs(), null, 2_000_000);
        c.setLineSink(out::add);
        for (int i = 0; i < 12; i++) c.tick(i * 500_000L);
        assertTrue(out.isEmpty());
    }

    @Test public void oneLineEveryTwoSecondsWithThePrefOn() {
        List<String> out = new ArrayList<>();
        StatsCollector c = new StatsCollector(new NoInputs(), null, 2_000_000);
        c.setLineSink(out::add);
        c.setAlwaysLog(true);
        for (int i = 1; i <= 12; i++) c.tick(i * 500_000L);   // 6 s of ticks
        assertEquals(3, out.size());
        assertTrue(out.get(0).startsWith("t=2000 "));         // Quest monotonic ms of the tick
    }

    @Test public void viewingThePageLogsForAWhileAfterTheLastLook() {
        List<String> out = new ArrayList<>();
        StatsCollector c = new StatsCollector(new NoInputs(), null, 2_000_000);
        c.setLineSink(out::add);
        c.markViewed(0);                                       // viewed at t = 0: logs until 2.5 s
        for (int i = 1; i <= 16; i++) c.tick(i * 500_000L);   // 8 s of ticks
        assertEquals(1, out.size());                           // only the 2 s tick falls inside
    }
}
