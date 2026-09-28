package com.openipc.pixelpilot.stats;

import static org.junit.Assert.*;

import com.openipc.xr.stats.StatsSnapshot;

import org.junit.Test;

public class LatencyWindowTest {
    private static final long OFFSET_US = 7_000_000_000L;   // air clock = Quest clock + 7000 s

    private static ClockSync syncedClock() {
        ClockSync c = new ClockSync(4);
        c.add(0, OFFSET_US + 500, OFFSET_US + 500, 1_000);     // rtt 1 ms, exact offset
        return c;
    }

    /** An air frame whose last packet left at Quest time {@code sentQuestUs}: 4 ms encode, 1 ms packetise+send. */
    private static SidecarProtocol.Frame air(long rtpTs, long sentQuestUs, int pkts, long bytes, boolean idr) {
        SidecarProtocol.Frame f = new SidecarProtocol.Frame();
        f.ssrc = 0xABCD;
        f.rtpTs = rtpTs;
        f.lastPktSendUs = sentQuestUs + OFFSET_US;
        f.frameReadyUs = f.lastPktSendUs - 1_000;
        f.captureUs = f.frameReadyUs - 4_000;
        f.seqCount = pkts;
        f.hasEncInfo = true;
        f.frameSizeBytes = bytes;
        f.frameType = idr ? SidecarProtocol.FRAME_TYPE_IDR : 0;
        return f;
    }

    /** The Quest side of the same frame: complete 3 ms after the air sent it, decoded 1.5 ms later. */
    private static QuestFrame quest(long rtpTs, long sentQuestUs) {
        long completeNs = (sentQuestUs + 3_000) * 1000;
        return new QuestFrame(0xABCD, rtpTs, completeNs, completeNs + 1_500_000);
    }

    @Test public void matchedFramesGiveEverySegmentAndTheSum() {
        LatencyWindow w = new LatencyWindow(2_000_000);
        DisplayEstimate display = decodedNs -> 2_000_000;   // 2 ms to the next predicted display
        for (int i = 0; i < 10; i++) {
            long sent = 10_000_000 + i * 6_000;
            w.addAir(air(90_000 + i * 540, sent, 12, 1500, false), sent + 2_000);
            w.addQuest(quest(90_000 + i * 540, sent));
        }
        StatsSnapshot s = w.fill(new StatsSnapshot.Builder(), 10_100_000, syncedClock(), display).build();
        assertEquals(10, s.matchedFrames);
        assertEquals(4.0, s.encode.p50Ms, 1e-9);
        assertEquals(1.0, s.airSend.p50Ms, 1e-9);
        assertEquals(3.0, s.link.p50Ms, 1e-9);
        assertEquals(1.5, s.decode.p50Ms, 1e-9);
        assertEquals(2.0, s.toDisplay.p50Ms, 1e-9);
        assertEquals(11.5, s.total.p50Ms, 1e-9);
        assertTrue(s.clockSynced);
        assertEquals(1.0, s.clockRttMs, 1e-9);
    }

    @Test public void theQuestSideMayArriveFirst() {
        LatencyWindow w = new LatencyWindow(2_000_000);
        w.addQuest(quest(500, 1_000_000));
        w.addAir(air(500, 1_000_000, 10, 1000, false), 1_002_000);
        StatsSnapshot s = w.fill(new StatsSnapshot.Builder(), 1_010_000, syncedClock(), null).build();
        assertEquals(1, s.matchedFrames);
        assertEquals(3.0, s.link.p50Ms, 1e-9);
        assertEquals(0, s.toDisplay.n);        // no display grid: no estimate
        assertEquals(0, s.total.n);            // and so no complete sum
    }

    @Test public void withoutAClockOnlyTheSameDeviceSegmentsAreKnown() {
        LatencyWindow w = new LatencyWindow(2_000_000);
        w.addAir(air(1, 1_000_000, 10, 1000, false), 1_002_000);
        w.addQuest(quest(1, 1_000_000));
        StatsSnapshot s = w.fill(new StatsSnapshot.Builder(), 1_010_000, new ClockSync(4), decodedNs -> 0).build();
        assertEquals(4.0, s.encode.p50Ms, 1e-9);
        assertEquals(1.5, s.decode.p50Ms, 1e-9);
        assertEquals(0, s.link.n);
        assertEquals(0, s.total.n);
        assertFalse(s.clockSynced);
    }

    @Test public void framesOlderThanTheWindowDropOut() {
        LatencyWindow w = new LatencyWindow(2_000_000);
        w.addAir(air(1, 1_000_000, 10, 1000, false), 1_002_000);
        w.addQuest(quest(1, 1_000_000));
        StatsSnapshot s = w.fill(new StatsSnapshot.Builder(), 5_000_000, syncedClock(), null).build();
        assertEquals(0, s.matchedFrames);
        assertEquals(0, s.encode.n);
    }

    @Test public void airSideRatesFromTheSidecarTrailer() {
        LatencyWindow w = new LatencyWindow(2_000_000);
        for (int i = 0; i < 100; i++) {   // 100 frames over 1 s, 2 of them IDR
            long t = 1_000_000 + i * 10_000;
            w.addAir(air(i, t, i < 50 ? 10 : 12, 2000, i == 10 || i == 60), t);
        }
        StatsSnapshot s = w.fill(new StatsSnapshot.Builder(), 2_000_000, syncedClock(), null).build();
        assertEquals(2 * 8 / 1.0, s.frameKbP50 * 1.0, 1e-9);   // 2000 B = 16 kbit
        assertEquals(11.0, s.pktsPerFrameP50, 1e-9);            // median of 50 × 10 and 50 × 12
        assertEquals(1.0, s.idrPerS, 1e-9);                     // 2 IDRs in a 2 s window
        assertEquals(10.0, s.sidecarAgeMs, 1e-9);               // newest sidecar frame 10 ms ago
    }

    @Test public void aNewStreamWithTheSameTimestampIsNotMatchedAcrossSsrc() {
        LatencyWindow w = new LatencyWindow(2_000_000);
        w.addAir(air(1, 1_000_000, 10, 1000, false), 1_002_000);
        w.addQuest(new QuestFrame(0x9999, 1, 4_000_000_000L, 4_001_500_000L));
        StatsSnapshot s = w.fill(new StatsSnapshot.Builder(), 1_010_000, syncedClock(), null).build();
        assertEquals(0, s.matchedFrames);
    }
}
