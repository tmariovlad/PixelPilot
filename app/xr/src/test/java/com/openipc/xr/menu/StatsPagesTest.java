package com.openipc.xr.menu;

import static org.junit.Assert.*;

import com.openipc.xr.stats.Segment;
import com.openipc.xr.stats.StatsSnapshot;

import java.util.List;

import org.junit.Test;

/** The Stats pages' text from a StatsSnapshot (docs/xr/menu-design.md §6): numbers formatted, unknowns as "-". */
public class StatsPagesTest {
    static StatsSnapshot full() {
        return new StatsSnapshot.Builder()
                .encode(Segment.of(new double[]{4.0, 4.2}))
                .airSend(Segment.of(new double[]{0.5}))
                .link(Segment.of(new double[]{7.9, 8.1}))
                .decode(Segment.of(new double[]{2.2}))
                .toDisplay(Segment.of(new double[]{6.0}))
                .total(Segment.of(new double[]{20.6, 21.0}))
                .matching(178, true, 3.2, 120)
                .rate(7, 1, 20, false, true, true, 97.5)
                .rssi(-58, -61).snr(17, 18)
                .loss(3.1, 0.74, 72, 5.1)
                .decoder(89.6, 0.2, 0)
                .levers(1.1, 0.0, 12.0)
                .air(43.0, 32, 1.1, 96)
                .build();
    }

    static String joined(List<String> l) {
        return String.join("\n", l);
    }

    @Test public void summaryCarriesG2gFpsLossRateAndSignal() {
        String s = joined(new StatsPages(StatsPagesTest::full).lines(StatsPages.SUMMARY));
        assertTrue(s, s.contains("G2G est."));
        assertTrue(s, s.contains("no sensor/panel"));
        assertTrue(s, s.contains("89.6"));
        assertTrue(s, s.contains("0.74 %"));
        assertTrue(s, s.contains("MCS7"));
        assertTrue(s, s.contains("-58 / -61 dBm"));
    }

    @Test public void latencyHasOneLinePerSegmentAndTheSum() {
        List<String> l = new StatsPages(StatsPagesTest::full).lines(StatsPages.LATENCY);
        String s = joined(l);
        for (String seg : new String[]{"capture>encoded", "encoded>sent", "sent>complete", "complete>decoded",
                "decoded>shown", "sum"}) {
            assertTrue(seg + " in " + s, s.contains(seg));
        }
        assertTrue(s, s.contains("178 frames"));
    }

    @Test public void missingSidecarGreysTheAirSegmentsAndTheSum() {
        StatsSnapshot noSidecar = new StatsSnapshot.Builder().decode(Segment.of(new double[]{2.2})).build();
        String s = joined(new StatsPages(() -> noSidecar).lines(StatsPages.LATENCY));
        assertTrue(s, s.contains("no sidecar"));
        assertTrue(s, s.contains("2.2"));
    }

    @Test public void unknownNumbersPrintAsADash() {
        String s = joined(new StatsPages(() -> StatsSnapshot.EMPTY).lines(StatsPages.LINK));
        assertFalse(s, s.contains("NaN"));
        assertFalse(s, s.contains(String.valueOf(StatsSnapshot.NA)));
        assertTrue(s, s.contains("-"));
    }

    @Test public void everyPageFitsTheMenuWidthAndAnUnknownPageIsEmpty() {
        StatsPages p = new StatsPages(StatsPagesTest::full);
        for (String id : StatsPages.PAGES) {
            List<String> l = p.lines(id);
            assertFalse(id, l.isEmpty());
            for (String line : l) assertTrue(id + ": " + line, line.length() <= MenuRenderer.COLUMNS);
        }
        assertTrue(p.lines("nope").isEmpty());
    }
}
