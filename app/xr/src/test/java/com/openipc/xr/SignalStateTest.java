package com.openipc.xr;

import static org.junit.Assert.*;

import com.openipc.xr.SignalState.Kind;
import com.openipc.xr.SignalState.Link;
import org.junit.Before;
import org.junit.Test;

public class SignalStateTest {
    private static final long MS = 1_000_000L;
    private static final long P = 11 * MS;                 // ~90 fps
    private static final long TICK = 250 * MS;
    private static final Link GOOD = new Link(1200, 1200, 0);
    private static final long[] NONE = new long[0];

    private SignalState s;
    private long now;

    @Before public void setUp() {
        s = new SignalState();
        now = 10_000 * MS;
        s.reset(now);
    }

    /** Frames every P during the last tick, ending at the current time. */
    private long[] framesThisTick() {
        int n = (int) (TICK / P);
        long[] t = new long[n];
        for (int i = 0; i < n; i++) t[i] = now - (n - 1 - i) * P;
        return t;
    }

    private Kind tick(long[] frames, boolean adapter, Link link) {
        return s.update(now, frames, P, adapter, link, 100 * MS);
    }

    /** No frames for 400 ms: past the 250 ms stall threshold. */
    private Kind stall(boolean adapter, Link link) {
        now += 400 * MS;
        return tick(NONE, adapter, link);
    }

    private Kind advance(long[] frames, boolean adapter, Link link) {
        now += TICK;
        return tick(frames == null ? framesThisTick() : frames, adapter, link);
    }

    @Test public void steadyFramesAreOk() {
        assertEquals(Kind.OK, advance(null, true, GOOD));
        assertEquals(Kind.OK, advance(null, true, GOOD));
        assertEquals("", s.message());
    }

    @Test public void noFrameYetIsWaitingForVideo() {
        assertEquals(Kind.WAITING_FOR_VIDEO, advance(NONE, true, GOOD));
        assertTrue(s.message().startsWith("WAITING FOR VIDEO"));
        assertFalse(s.needsAction());
    }

    @Test public void framesStoppingWhilePacketsFlowIsAStall() {
        advance(null, true, GOOD);
        now += 400 * MS;
        assertEquals(Kind.VIDEO_STALLED, tick(NONE, true, new Link(1300, 1300, 0)));
        assertEquals("VIDEO STALLED (0.4 s)", s.message());
    }

    @Test public void shortGapUnderTheThresholdStaysOk() {
        advance(null, true, GOOD);
        now += 200 * MS;                                   // < 250 ms and < 6 frame periods at 30 fps
        assertEquals(Kind.OK, s.update(now, NONE, 33 * MS, true, GOOD, 100 * MS));
    }

    @Test public void thresholdScalesWithSlowFrameRates() {
        advance(null, true, GOOD);
        now += 300 * MS;                                   // 6 periods at 20 fps = 300 ms: not yet stalled
        assertEquals(Kind.OK, s.update(now, NONE, 50 * MS, true, GOOD, 100 * MS));
        now += 50 * MS;
        assertEquals(Kind.VIDEO_STALLED, s.update(now, NONE, 50 * MS, true, new Link(9, 9, 0), 100 * MS));
    }

    @Test public void noPacketsIsNoSignal() {
        advance(null, true, GOOD);
        assertEquals(Kind.NO_PACKETS, stall(true, new Link(0, 0, 0)));
        assertTrue(s.message().startsWith("NO SIGNAL"));
        assertTrue(s.needsAction());
    }

    @Test public void repeatedCountersAreNotSecondGuessed() {
        // The native side owns the dead-link signal; identical windows alone mean nothing here.
        Link same = new Link(1200, 1200, 0);
        advance(null, true, same);
        assertEquals(Kind.VIDEO_STALLED, stall(true, same));
    }

    @Test public void staleStatsCountAsNoPackets() {
        advance(null, true, GOOD);
        now += 400 * MS;
        assertEquals(Kind.NO_PACKETS, s.update(now, NONE, P, true, GOOD, 5_000 * MS));
    }

    private static final Link ALL_FAIL = new Link(145, 0, 145);   // as seen after an RTL replug, 2026-09-28

    @Test public void packetsThatKeepFailingToDecryptAreAWrongKey() {
        advance(null, true, GOOD);
        Kind k = Kind.OK;
        for (long t = 0; t <= SignalState.WRONG_KEY_NS + TICK; t += TICK) k = advance(NONE, true, ALL_FAIL);
        assertEquals(Kind.WRONG_KEY, k);
        assertTrue(s.message().startsWith("WRONG KEY"));
    }

    @Test public void aWrongKeyFromTheStartIsNamedToo() {
        Kind k = Kind.OK;
        for (long t = 0; t <= SignalState.WRONG_KEY_NS + TICK; t += TICK) k = advance(NONE, true, ALL_FAIL);
        assertEquals(Kind.WRONG_KEY, k);
    }

    @Test public void aShortAllFailingSpellIsNotAWrongKey() {
        // the replug case: ~1 s of windows where every packet fails, then the video comes back
        advance(null, true, GOOD);
        for (int i = 0; i < 4; i++) assertNotEquals(Kind.WRONG_KEY, advance(NONE, true, ALL_FAIL));
        assertEquals(Kind.VIDEO_STALLED, s.kind());
        advance(null, true, GOOD);
        for (int i = 0; i < 6; i++) advance(null, true, GOOD);
        assertEquals(Kind.OK, s.kind());
    }

    @Test public void aGoodWindowRestartsTheWrongKeyClock() {
        advance(null, true, GOOD);
        for (int i = 0; i < 6; i++) advance(NONE, true, ALL_FAIL);     // 1.5 s
        advance(NONE, true, new Link(100, 3, 97));                      // some packets decrypt
        for (int i = 0; i < 6; i++) assertNotEquals(Kind.WRONG_KEY, advance(NONE, true, ALL_FAIL));
    }

    @Test public void noAdapterTakesPriorityWhenNoFramesArrive() {
        assertEquals(Kind.NO_ADAPTER, advance(NONE, false, Link.NONE));
    }

    @Test public void framesOverUdpWithoutAnAdapterAreOk() {
        // APFPV over the Quest's own Wi-Fi: no adapter, video still arrives
        advance(null, false, Link.NONE);
        assertEquals(Kind.OK, advance(null, false, Link.NONE));
    }

    @Test public void recoveryNeedsFiveFreshFrames() {
        advance(null, true, GOOD);
        assertEquals(Kind.NO_PACKETS, stall(true, Link.NONE));
        now += TICK;
        long[] two = {now - P, now};
        assertEquals(Kind.NO_PACKETS, tick(two, true, GOOD));
        assertEquals("VIDEO RESUMING", s.message());
        assertFalse(s.needsAction());
        now += 3 * P;
        long[] three = {now - 2 * P, now - P, now};
        assertEquals(Kind.OK, tick(three, true, GOOD));
    }

    @Test public void oldFramesDoNotCountTowardsRecovery() {
        advance(null, true, GOOD);
        long lastGood = now;
        assertEquals(Kind.NO_PACKETS, stall(true, Link.NONE));
        now += TICK;
        long[] replay = {lastGood - 2 * P, lastGood - P, lastGood};   // not newer than the last frame seen
        assertEquals(Kind.NO_PACKETS, tick(replay, true, Link.NONE));
    }

    @Test public void resetForgetsThePreviousAttachment() {
        advance(null, true, GOOD);
        now += TICK;
        s.reset(now);
        assertEquals(Kind.WAITING_FOR_VIDEO, s.kind());
        now += 400 * MS;
        assertEquals(Kind.WAITING_FOR_VIDEO, tick(NONE, true, GOOD));
    }

    @Test public void framesFromBeforeTheAttachmentAreIgnored() {
        long before = now - 5 * MS;                        // queued by the previous decoder, drained after reset
        now += 100 * MS;
        assertEquals(Kind.WAITING_FOR_VIDEO, tick(new long[]{before, before + MS}, true, GOOD));
    }

    @Test public void configErrorComesFirstWhenNoFramesArrive() {
        s.setConfigError("gs.key 32 B, needs 64");
        assertEquals(Kind.CONFIG_ERROR, advance(NONE, false, Link.NONE));
        assertEquals("SETUP: gs.key 32 B, needs 64", s.message());
        assertTrue(s.needsAction());
    }

    @Test public void framesStillWinOverAConfigError() {
        s.setConfigError("no gs.key");                     // e.g. RTP pushed over Wi-Fi without a link
        advance(null, false, Link.NONE);
        assertEquals(Kind.OK, advance(null, false, Link.NONE));
    }

    @Test public void everyHeadlineFitsTheBand() {
        for (Kind k : Kind.values()) {
            String m = SignalState.message(k, 123_400_000_000L);   // a long "x s" still fits
            assertTrue(k + ": " + m, m.length() <= 40);
        }
    }
    // freeze_until_idr holds the last good frame until a key frame: no decoded frames, packets arriving. That is a HOLD,
    // not a stall (docs/xr/link-envelope.md, "IDR + freeze in use"): no alarm, and it names the wait.
    private Kind hold(boolean holding, Link link) {
        now += 400 * MS;
        return s.update(now, NONE, P, true, link, 100 * MS, holding);
    }

    @Test public void aFreezeWaitingForTheKeyFrameIsAHoldNotAStall() {
        advance(null, true, GOOD);
        assertEquals(Kind.HOLD, hold(true, GOOD));
        assertFalse(s.needsAction());
        assertTrue(s.message(), s.message().startsWith("HOLD - WAITING FOR KEYFRAME"));
        assertTrue(s.message().length() <= 40);
    }

    @Test public void withoutPacketsAHoldIsStillNoSignal() {
        advance(null, true, GOOD);
        assertEquals(Kind.NO_PACKETS, hold(true, new Link(0, 0, 0)));
    }

    @Test public void notHoldingIsTheUsualStall() {
        advance(null, true, GOOD);
        assertEquals(Kind.VIDEO_STALLED, hold(false, GOOD));
        assertTrue(s.needsAction());
    }

    @Test public void theKeyFrameAfterAHoldIsOkAtOnce() {
        advance(null, true, GOOD);
        hold(true, GOOD);
        now += P;
        assertEquals(Kind.OK, s.update(now, new long[]{now}, P, true, GOOD, 100 * MS, false));
        assertEquals("", s.message());
    }

    // A preset switch from the menu stops the stream for ~3 s by design (docs/xr/presets-design.md, "What a mode
    // switch costs"): the gap is expected, so it is SWITCHING, not a fault, whatever the link shows meanwhile.
    @Test public void anExpectedSwitchGapIsSwitchingNotAFault() {
        advance(null, true, GOOD);
        s.setSwitching(true);
        assertEquals(Kind.SWITCHING, stall(true, new Link(0, 0, 0)));   // no packets while the air restarts
        assertFalse(s.needsAction());
        assertTrue(s.message(), s.message().startsWith("SWITCHING MODE"));
        assertEquals(Kind.SWITCHING, stall(true, GOOD));                 // packets back, no frame yet
        assertEquals(Kind.SWITCHING, hold(true, GOOD));                  // a hold during the switch too
    }

    @Test public void aSwitchDoesNotHideARealFault() {
        advance(null, true, GOOD);
        s.setSwitching(true);
        assertEquals(Kind.NO_ADAPTER, stall(false, GOOD));
        s.setConfigError("bad gs.key");
        assertEquals(Kind.CONFIG_ERROR, stall(true, GOOD));
    }

    @Test public void whenTheSwitchEndsWithoutVideoTheStallIsReported() {
        advance(null, true, GOOD);
        s.setSwitching(true);
        stall(true, GOOD);
        s.setSwitching(false);                                            // e.g. the air reverted and still no frames
        assertEquals(Kind.VIDEO_STALLED, stall(true, GOOD));
        assertTrue(s.needsAction());
    }

    @Test public void framesDuringASwitchAreOk() {
        s.setSwitching(true);
        assertEquals(Kind.OK, advance(null, true, GOOD));                 // the old mode still plays until the gap
    }
}
