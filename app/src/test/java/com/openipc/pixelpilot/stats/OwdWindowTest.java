package com.openipc.pixelpilot.stats;

import static org.junit.Assert.*;

import org.junit.Test;

/**
 * The relative one-way delay (first packet's arrival − RTP timestamp / 90 kHz), detrended by the clock drift, minus its
 * running minimum over OwdWindow.BASELINE_NS = queueing delay, without the sidecar or a clock sync
 * (docs/xr/stats-backend.md §7, §7.1).
 */
public class OwdWindowTest {
    private static final long MS = 1_000_000L;          // ns
    private static final long WINDOW_US = 2_000_000L;
    /** The air/Quest clock drift measured in all 5 captures of 2026-09-30 (stats-backend §7.1), ms per s. */
    private static final double MEASURED_DRIFT_MS_PER_S = 0.07;

    /** Frames at 120 fps (750 ticks of 90 kHz), the first packet arriving baseMs + extraMs after capture, plus the real
     * air/Quest clock drift, which OwdWindow learns and takes out. */
    private static void feed(OwdWindow w, long ssrc, long ts0, int from, int n, double baseMs, double extraMs) {
        for (int i = from; i < from + n; i++) {
            long ts = (ts0 + 750L * i) & 0xFFFFFFFFL;
            long captureNs = 1_000_000_000L + (long) (i * (1e9 / 120));
            double driftMs = MEASURED_DRIFT_MS_PER_S * (captureNs / 1e9);
            long firstNs = captureNs + (long) ((baseMs + extraMs + driftMs) * MS);
            w.add(new QuestFrame(ssrc, ts, firstNs + 3 * MS, firstNs + 5 * MS, firstNs));
        }
    }

    private static long nowUs(int frame) {
        return (1_000_000_000L + (long) (frame * (1e9 / 120))) / 1000 + 20_000;
    }

    @Test public void aConstantDelayReadsZero() {
        OwdWindow w = new OwdWindow(WINDOW_US);
        feed(w, 1, 0, 0, 1200, 12.0, 0);
        OwdWindow.Stats s = w.snapshot(nowUs(1200));
        assertTrue(s.windowed.n > 200);
        assertEquals(0.0, s.windowed.p50Ms, 0.05);
        assertEquals(0.0, s.windowed.p95Ms, 0.05);
        assertEquals(0.0, s.unbounded.p95Ms, 0.05);
    }

    @Test public void aQueueStepReadsAsItsSize() {
        OwdWindow w = new OwdWindow(WINDOW_US);
        feed(w, 1, 0, 0, 1200, 12.0, 0);          // 10 s at the base delay
        feed(w, 1, 0, 1200, 240, 12.0, 20.0);     // 2 s with 20 ms of queue
        OwdWindow.Stats s = w.snapshot(nowUs(1440));
        assertEquals(20.0, s.windowed.p50Ms, 0.1);
    }

    @Test public void aStandingQueueLongerThanTenSecondsStillReadsAsItsSize() {
        // 36's finding (§7.1): a short base hides a standing queue; m6b25f46's +55 ms read 3-5 ms with a 2-10 s base
        OwdWindow w = new OwdWindow(WINDOW_US);
        feed(w, 1, 0, 0, 8400, 12.0, 0);          // 70 s clean: the drift fit is past its bootstrap (6 blocks)
        feed(w, 1, 0, 8400, 4800, 12.0, 55.0);    // then 40 s with 55 ms of queue
        OwdWindow.Stats s = w.snapshot(nowUs(13200));
        assertEquals(55.0, s.windowed.p50Ms, 0.5);
        assertEquals(55.0, s.unbounded.p50Ms, 0.5);
    }

    @Test public void theClockDriftIsTakenOutBeforeTheMinimum() {
        // 75 s of a clean link with the real drift: an uncorrected 60 s minimum would read ~4 ms here
        OwdWindow w = new OwdWindow(WINDOW_US);
        feed(w, 1, 0, 0, 9000, 12.0, 0);
        assertEquals(0.0, w.snapshot(nowUs(9000)).windowed.p95Ms, 0.05);
    }

    @Test public void aWrappingRtpTimestampDoesNotRestartTheBaseline() {
        // a queue that starts right at the wrap: a spurious restart there would rebuild the base from the queue (0)
        OwdWindow w = new OwdWindow(WINDOW_US);
        long ts0 = 0xFFFFFFFFL - 750L * 1199;          // wraps at frame 1200
        feed(w, 1, ts0, 0, 1200, 12.0, 0);
        feed(w, 1, ts0, 1200, 360, 12.0, 20.0);
        assertEquals(20.0, w.snapshot(nowUs(1560)).windowed.p50Ms, 0.1);
    }

    @Test public void aNewTimestampBaseOrStreamResetsTheBaseline() {
        OwdWindow w = new OwdWindow(WINDOW_US);
        feed(w, 1, 500_000_000L, 0, 600, 12.0, 0);
        feed(w, 1, 1_000L, 600, 600, 12.0, 0);          // waybeam restarted: a new, LOWER RTP base (the delay jumps up)
        assertEquals(0.0, w.snapshot(nowUs(1200)).windowed.p95Ms, 0.05);
        feed(w, 1, 900_000_000L, 1200, 600, 12.0, 0);   // and a higher one (the delay jumps down)
        assertEquals(0.0, w.snapshot(nowUs(1800)).windowed.p95Ms, 0.05);
        // a new SSRC whose timestamps happen to continue, 30 ms slower: under the 1000 ms jump rule, so only the
        // SSRC reset keeps it from reading as a 30 ms queue
        feed(w, 2, 900_000_000L, 1800, 600, 42.0, 0);
        assertEquals(0.0, w.snapshot(nowUs(2400)).windowed.p95Ms, 0.05);
    }

    @Test public void framesWithoutAFirstPacketTimeAreIgnored() {
        OwdWindow w = new OwdWindow(WINDOW_US);
        w.add(new QuestFrame(1, 0, 5 * MS, 6 * MS, 0));
        assertEquals(0, w.snapshot(10_000).windowed.n);
    }
}
