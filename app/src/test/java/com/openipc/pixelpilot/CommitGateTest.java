package com.openipc.pixelpilot;

import static org.junit.Assert.*;

import org.junit.Test;

public class CommitGateTest {
    @Test public void commitsAfterEnoughFramesAtTheNewSizeOnceArmed() {
        CommitGate g = new CommitGate();
        g.expect("t1", 848, 480);
        g.arm();
        assertNull(g.onFrames(20, 848, 480));
        assertEquals("t1", g.onFrames(10, 848, 480));
        assertNull(g.onFrames(50, 848, 480));      // once
        assertFalse(g.waiting());
    }

    @Test public void framesBeforeTheAirSaysPendingDoNotCount() {
        // 848x480 -> 848x480 (Balanced-lite -> Wide): the old stream has the new size too
        CommitGate g = new CommitGate();
        g.expect("t1", 848, 480);
        assertNull(g.onFrames(100, 848, 480));
        g.arm();
        assertNull(g.onFrames(29, 848, 480));
        assertEquals("t1", g.onFrames(1, 848, 480));
    }

    @Test public void framesAtAnotherSizeDoNotCount() {
        CommitGate g = new CommitGate();
        g.expect("t1", 1280, 720);
        g.arm();
        assertNull(g.onFrames(100, 640, 480));
    }

    @Test public void armWithoutAnApplyDoesNothing() {
        CommitGate g = new CommitGate();
        g.arm();
        assertNull(g.onFrames(100, 640, 480));
    }
}
