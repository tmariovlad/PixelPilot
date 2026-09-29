package com.openipc.pixelpilot.stats;

import static org.junit.Assert.*;

import com.openipc.xr.stats.Segment;
import com.openipc.xr.stats.StatsSnapshot;

import java.util.ArrayList;
import java.util.List;

import org.junit.Test;

public class HealthMonitorTest {
    private final List<String> events = new ArrayList<>();
    private final List<String> health = new ArrayList<>();
    private final HealthMonitor m = new HealthMonitor((tag, line) -> {
        if (tag.equals(HealthMonitor.EVENT_TAG)) events.add(line);
        else if (tag.equals(HealthMonitor.HEALTH_TAG)) health.add(line);
    }, mono -> mono + 1_700_000_000_000L);   // wall = mono + a fixed epoch offset

    /** counters: idrOk, idrFailed, frozenSlices, decoderRebuilds, codecSwitches. */
    private static long[] c(long ok, long fail, long frozen, long rebuilds, long switches) {
        return new long[]{ok, fail, frozen, rebuilds, switches};
    }

    private String only(String code) {
        List<String> hits = new ArrayList<>();
        for (String e : events) if (e.contains(" code=" + code + " ")) hits.add(e);
        assertEquals("events with code " + code + ": " + events, 1, hits.size());
        return hits.get(0);
    }

    @Test public void lineFormatHasBothClocksCodeAndLevel() {
        m.onSession(1000, false);
        String e = only("SESSION_INACTIVE");
        assertTrue(e, e.startsWith("t_mono_ms=1000 t_wall_ms=1700000001000 code=SESSION_INACTIVE level=ALERT"));
        assertFalse(e.contains("\n"));
    }

    @Test public void aStallAndItsRecoveryWithDuration() {
        m.onTick(0, "OK", true, c(0, 0, 0, 0, 0));
        m.onTick(250, "VIDEO_STALLED", true, c(0, 0, 0, 0, 0));
        m.onTick(1250, "OK", true, c(0, 0, 0, 0, 0));
        String lost = only("SIGNAL_LOST");
        assertTrue(lost, lost.contains(" level=ALERT to=VIDEO_STALLED cause=stall"));
        String ok = only("SIGNAL_OK");
        assertTrue(ok, ok.contains(" was=VIDEO_STALLED dur_ms=1000 cause=stall"));
    }

    // A menu-initiated preset switch: SignalState reports SWITCHING for the expected gap (docs/xr/presets-design.md).
    // It is logged as its own event, not a SIGNAL_LOST, and does not count as a stall.
    @Test public void anExpectedSwitchGapIsASwitchEventNotAStall() {
        m.onTick(0, "OK", true, c(0, 0, 0, 0, 0));
        m.onTick(250, "SWITCHING", false, c(0, 0, 0, 0, 0));
        m.onTick(3500, "OK", true, c(0, 0, 0, 0, 0));
        String gap = only("SWITCH_GAP");
        assertTrue(gap, gap.contains(" level=INFO"));
        String end = only("SWITCH_END");
        assertTrue(end, end.contains(" level=INFO dur_ms=3250"));
        for (String e : events) assertFalse(e, e.contains("SIGNAL_LOST") || e.contains("SIGNAL_OK"));
    }

    @Test public void aStallAfterASwitchThatEndedWithoutVideoIsStillAStall() {
        m.onTick(0, "OK", true, c(0, 0, 0, 0, 0));
        m.onTick(250, "SWITCHING", false, c(0, 0, 0, 0, 0));
        m.onTick(3500, "VIDEO_STALLED", true, c(0, 0, 0, 0, 0));        // the air reverted, still no video
        String end = only("SWITCH_END");
        assertTrue(end, end.contains(" dur_ms=3250 to=VIDEO_STALLED"));
        String lost = only("SIGNAL_LOST");
        assertTrue(lost, lost.contains(" level=ALERT to=VIDEO_STALLED cause=stall"));
        m.onTick(4500, "OK", true, c(0, 0, 0, 0, 0));
        assertTrue(only("SIGNAL_OK").contains(" dur_ms=1000 cause=stall"));
    }

    @Test public void aSwitchGapIsNotInTheStallsPerMinute() {
        for (int t = 0; t < 10_000; t += 250) {
            String kind = (t >= 2_000 && t < 5_000) ? "SWITCHING" : "OK";
            m.onTick(t, kind, !kind.equals("SWITCHING"), c(0, 0, 0, 0, 0));
        }
        m.onTick(10_000, "OK", true, c(0, 0, 0, 0, 0));
        String h = health.get(0);
        assertTrue(h, h.contains(" stalls_min=0.0 "));
    }

    @Test public void aHoldIsAWarningCausedByTheFreeze() {
        m.onTick(0, "OK", true, c(0, 0, 0, 0, 0));
        m.onTick(250, "HOLD", false, c(0, 0, 5, 0, 0));
        String lost = only("SIGNAL_LOST");
        assertTrue(lost, lost.contains(" level=WARN to=HOLD cause=freeze"));
    }

    @Test public void aStallWhileFreezeDropsSlicesIsCausedByTheFreeze() {
        m.onTick(0, "OK", true, c(0, 0, 10, 0, 0));
        m.onTick(250, "VIDEO_STALLED", true, c(0, 0, 14, 0, 0));
        assertTrue(only("SIGNAL_LOST").contains(" cause=freeze"));
    }

    @Test public void aStallRightAfterADecoderRebuildIsCausedByTheDecoder() {
        m.onTick(0, "OK", true, c(0, 0, 0, 0, 0));
        m.onTick(250, "OK", true, c(0, 0, 0, 1, 0));
        m.onTick(500, "VIDEO_STALLED", true, c(0, 0, 0, 1, 0));
        assertTrue(only("DECODER_REBUILD").contains(" level=WARN n=1"));
        assertTrue(only("SIGNAL_LOST").contains(" cause=decoder"));
    }

    @Test public void noPacketsIsNamedAsSuch() {
        m.onTick(0, "OK", true, c(0, 0, 0, 0, 0));
        m.onTick(250, "NO_PACKETS", true, c(0, 0, 0, 0, 0));
        assertTrue(only("SIGNAL_LOST").contains(" to=NO_PACKETS cause=no_packets"));
    }

    @Test public void freezeStartAndEndAfterTheCounterStops() {
        m.onTick(0, "OK", true, c(0, 0, 0, 0, 0));
        m.onTick(250, "OK", true, c(0, 0, 3, 0, 0));      // freeze starts
        m.onTick(500, "OK", true, c(0, 0, 7, 0, 0));
        m.onTick(750, "OK", true, c(0, 0, 7, 0, 0));      // stopped dropping
        assertTrue(events.stream().noneMatch(e -> e.contains("FREEZE_END")));
        m.onTick(1250, "OK", true, c(0, 0, 7, 0, 0));     // idle for >= 500 ms: over
        assertTrue(only("FREEZE_START").contains(" level=WARN"));
        String end = only("FREEZE_END");
        assertTrue(end, end.contains(" dur_ms=250 slices=7"));
    }

    @Test public void idrRequestsAreAggregatedAtMostOncePerSecond() {
        m.onTick(0, "OK", true, c(0, 0, 0, 0, 0));
        m.onTick(250, "OK", true, c(2, 0, 0, 0, 0));
        m.onTick(500, "OK", true, c(3, 1, 0, 0, 0));
        assertTrue(events.stream().noneMatch(e -> e.contains("code=IDR")));
        m.onTick(1000, "OK", true, c(3, 1, 0, 0, 0));
        String e = only("IDR_FAILED");
        assertTrue(e, e.contains(" level=WARN ok=3 failed=1"));
    }

    @Test public void idrFailuresCarryTheirReasons() {
        // leverCounters() with IdrRequester's per-result counters (2c86204): [5..10] = ok, refused, connect_timeout,
        // reply_timeout, http_status, error
        m.onTick(0, "OK", true, new long[]{0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0});
        m.onTick(250, "OK", true, new long[]{1, 3, 0, 0, 0, 1, 0, 2, 1, 0, 0});
        m.onTick(1000, "OK", true, new long[]{1, 3, 0, 0, 0, 1, 0, 2, 1, 0, 0});
        String e = only("IDR_FAILED");
        assertTrue(e, e.endsWith(" ok=1 failed=3 connect_timeout=2 reply_timeout=1"));
    }

    @Test public void idrLinesCarryTheHandshakeOfTheirRequests() {
        // [11..14] = connect attempts started, requests won by attempt >= 2, connect ms sum, requests connected
        // (IdrRequester's connect race, 2026-09-29)
        m.onTick(0, "OK", true, new long[]{0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0});
        m.onTick(250, "OK", true, new long[]{2, 1, 0, 0, 0, 2, 0, 1, 0, 0, 0, 11, 1, 180, 2});
        m.onTick(1000, "OK", true, new long[]{3, 1, 0, 0, 0, 3, 0, 1, 0, 0, 0, 12, 1, 190, 3});
        String e = only("IDR_FAILED");
        // 3 ok + 1 connect_timeout (7 SYNs): 12 attempts, 1 won late, mean connect 190/3 = 63 ms
        assertTrue(e, e.endsWith(" ok=3 failed=1 connect_timeout=1 attempts=12 late=1 connected=3 connect_ms=63"));
    }

    @Test public void idrLinesWithoutHandshakeCountersStayAsBefore() {
        m.onTick(0, "OK", true, c(0, 0, 0, 0, 0));
        m.onTick(1000, "OK", true, c(2, 0, 0, 0, 0));
        String e = only("IDR");
        assertTrue(e, e.endsWith(" ok=2 failed=0"));
    }

    @Test public void codecSwitchIsInfo() {
        m.onTick(0, "OK", true, c(0, 0, 0, 0, 0));
        m.onTick(250, "OK", true, c(0, 0, 0, 0, 1));
        assertTrue(only("CODEC_SWITCH").contains(" level=INFO n=1"));
    }

    @Test public void sessionOffAndOnWithTheTimeOff() {
        m.onSession(1000, false);
        m.onSession(4500, true);
        assertTrue(only("SESSION_INACTIVE").contains(" level=ALERT"));
        assertTrue(only("SESSION_ACTIVE").contains(" level=INFO off_ms=3500"));
    }

    @Test public void adapterGoneAndBackWithTheTimeToRecover() {
        m.onAdapter(0, true);                              // the first observation is a baseline, not an event
        m.onAdapter(1000, false);
        m.onAdapter(3200, true);
        assertTrue(only("ADAPTER_GONE").contains(" level=ALERT"));
        assertTrue(only("ADAPTER_BACK").contains(" gone_ms=2200"));
    }

    @Test public void linkStatusTextsWithoutSpacesAndWithoutRepeats() {
        m.onLinkStatus(0, "link lost - restarting (1)");
        m.onLinkStatus(100, "link lost - restarting (1)");
        assertTrue(only("LINK_STATUS").contains(" msg=link_lost_-_restarting_(1)"));
    }

    private static StatsSnapshot snap(double fps, double holes) {
        return new StatsSnapshot.Builder().fpsDecoded(fps).loss(4, 0.5, 70, holes).rssi(-50, -52).snr(20, 19)
                .decode(Segment.of(new double[]{1.5})).build();
    }

    @Test public void anFpsDropBelowSeventyPercentOfTheMedianForTwoSeconds() {
        for (int t = 0; t <= 10_000; t += 500) m.onSnapshot(t, snap(166, 0));
        for (int t = 10_500; t <= 12_000; t += 500) m.onSnapshot(t, snap(80, 0));
        assertTrue(events.stream().noneMatch(e -> e.contains("FPS_LOW")));   // 1.5 s low: not yet
        m.onSnapshot(12_500, snap(80, 0));
        assertTrue(only("FPS_LOW").contains(" level=WARN fps=80.0 median=166.0"));
        m.onSnapshot(13_000, snap(160, 0));
        assertTrue(only("FPS_OK").contains(" dur_ms=2500"));
    }

    @Test public void aLossBurstAboveTwentyHolesPerSecond() {
        m.onSnapshot(0, snap(166, 2));
        m.onSnapshot(500, snap(166, 35));
        m.onSnapshot(1000, snap(166, 50));
        m.onSnapshot(1500, snap(166, 5));
        assertTrue(only("LOSS_BURST").contains(" level=WARN holes=35.0"));
        assertTrue(only("LOSS_END").contains(" dur_ms=1000 peak=50.0"));
    }

    @Test public void healthEveryTenSecondsWithFreezePercentAndStallsPerMinute() {
        m.onSnapshot(0, snap(150, 3));
        long frozen = 0;
        for (int t = 0; t < 10_000; t += 250) {
            boolean freezing = t >= 2_000 && t < 4_500;            // 2.5 s of 10 s
            if (freezing) frozen += 2;
            String kind = (t >= 6_000 && t < 6_500) ? "VIDEO_STALLED" : "OK";   // one stall
            m.onTick(t, kind, true, c(t / 1000, 0, frozen, 0, 0));
        }
        assertTrue(health.isEmpty());
        m.onTick(10_000, "OK", true, c(10, 0, frozen, 0, 0));
        assertEquals(1, health.size());
        String h = health.get(0);
        assertTrue(h, h.contains(" code=HEALTH level=INFO win_s=10 "));
        assertTrue(h, h.contains(" frozen_pct=25.0 "));
        assertTrue(h, h.contains(" stalls_min=6.0 "));
        assertTrue(h, h.contains(" fps=150.0 "));
        assertTrue(h, h.contains(" idr_ok=1.00 idr_fail=0.00 "));
        assertTrue(h, h.contains(" rssiA=-50 rssiB=-52 snrA=20 snrB=19 dec_ms=1.50 kind=OK"));
    }
}
