package com.openipc.pixelpilot;

import static org.junit.Assert.*;

import org.junit.After;
import org.junit.Test;

public class XrPresenceTest {
    @After public void reset() {
        while (XrPresence.started()) XrPresence.onStop();
    }

    @Test public void startedBetweenStartAndStop() {
        assertFalse(XrPresence.started());
        XrPresence.onStart();
        assertTrue(XrPresence.started());
        XrPresence.onStop();
        assertFalse(XrPresence.started());
    }

    @Test public void anOverlappingRelaunchStaysStarted() {
        // the new instance starts before the old one stops (onNewIntent -> recreate)
        XrPresence.onStart();
        XrPresence.onStart();
        XrPresence.onStop();
        assertTrue(XrPresence.started());
    }

    @Test public void anExtraStopNeverGoesNegative() {
        XrPresence.onStop();
        XrPresence.onStart();
        assertTrue(XrPresence.started());
    }
}
