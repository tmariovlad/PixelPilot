package com.openipc.pixelpilot.stats;

import static org.junit.Assert.*;

import com.openipc.xr.stats.StatsSnapshot;

import java.util.ArrayList;
import java.util.List;

import org.junit.Test;

public class StatsCollectorTest {
    @Test public void gridEstimateIsTheTimeToTheNextPredictedDisplay() {
        DisplayEstimate d = GridDisplayEstimate.of(1_000_000_000L, 8_333_333L, true);
        assertEquals(3_333_333L, d.nsToDisplay(1_005_000_000L));            // next display at +8.33 ms
        assertEquals(0L, d.nsToDisplay(1_000_000_000L));                    // exactly on a display
        assertEquals(5_000_000L, d.nsToDisplay(1_000_000_000L - 5_000_000)); // before the anchor: the anchor itself
        assertEquals(1_000_000L, d.nsToDisplay(1_000_000_000L - 9_333_333)); // more than a period before
        assertEquals(-1L, GridDisplayEstimate.of(1, 0, true).nsToDisplay(5)); // no grid yet
        assertEquals(-1L, GridDisplayEstimate.of(1, 8_333_333L, false).nsToDisplay(5)); // not CLOCK_MONOTONIC
    }

    @Test public void counterRateOverTheWindow() {
        CounterRate r = new CounterRate(2_000_000);
        assertTrue(Double.isNaN(r.perSecond()));
        r.add(1_000_000, 10);
        r.add(2_000_000, 14);
        r.add(3_000_000, 20);
        assertEquals(5.0, r.perSecond(), 1e-9);           // (20 - 10) / 2 s
        r.add(6_000_000, 20);                              // the old samples age out
        assertTrue(Double.isNaN(r.perSecond()));           // one sample: no rate yet
    }

    /** Inputs as the XR activity would feed them, with a scripted clock. */
    private static final class Fake implements StatsCollector.Inputs {
        final List<long[]> frames = new ArrayList<>();
        long idrOk, idrFailed, frozen;
        int[] rate = {0x0E, 0, 1, 1, 0, 190, 200};

        @Override public long[] drainFrameTimes() { return frames.isEmpty() ? new long[0] : frames.remove(0); }
        @Override public long[] leverCounters() { return new long[]{idrOk, idrFailed, frozen}; }
        @Override public int[] takeRxRate() { return rate; }
        @Override public DisplayEstimate display() { return decodedNs -> 2_000_000; }
    }

    @Test public void aTickCombinesLatencyLinkDecoderAndLevers() {
        Fake in = new Fake();
        StatsCollector c = new StatsCollector(in, null, 2_000_000);
        long t0 = 10_000_000;
        // one frame seen by the air and by the Quest, with the sidecar clock in step (offset 0, rtt 1 ms)
        c.clock().add(0, 500, 500, 1_000);
        SidecarProtocol.Frame f = new SidecarProtocol.Frame();
        f.ssrc = 7;
        f.rtpTs = 900;
        f.captureUs = t0;
        f.frameReadyUs = t0 + 4_000;
        f.lastPktSendUs = t0 + 5_000;
        c.onSidecarFrame(f, t0 + 6_000);
        in.frames.add(new long[]{7, 900, (t0 + 8_000) * 1000, (t0 + 9_500) * 1000});
        c.onLinkStats(t0, 1000, 50, 10, 1, 74, 70, 50, 40);
        c.onDecodedFps(166.5f);
        c.tick(t0 + 10_000);
        in.idrOk = 4;
        in.frozen = 30;
        c.tick(t0 + 1_010_000);
        StatsSnapshot s = c.snapshot();
        assertEquals(1, s.matchedFrames);
        assertEquals(4.0, s.encode.p50Ms, 1e-9);
        assertEquals(3.0, s.link.p50Ms, 1e-9);
        assertEquals(1.5, s.decode.p50Ms, 1e-9);
        assertEquals(2.0, s.toDisplay.p50Ms, 1e-9);
        assertEquals(11.5, s.total.p50Ms, 1e-9);
        assertEquals(2, s.mcs);
        assertEquals(-36, s.rssiADbm);
        assertEquals(166.5, s.fpsDecoded, 1e-6);
        assertEquals(4.0, s.idrReqOkPerS, 1e-9);
        assertEquals(0.0, s.idrReqFailedPerS, 1e-9);
        assertEquals(30.0, s.frozenSlicesPerS, 1e-9);
        assertEquals(1, s.decErr);
    }

    @Test public void beforeTheFirstTickTheSnapshotIsEmpty() {
        StatsCollector c = new StatsCollector(new Fake(), null, 2_000_000);
        assertSame(StatsSnapshot.EMPTY, c.snapshot());
    }
}
