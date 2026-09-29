package com.openipc.xr;

import static org.junit.Assert.*;

import org.junit.Test;

public class PresetStatusTest {
    @Test public void countsDownWhileSwitching() {
        PresetStatus s = new PresetStatus();
        s.switching("Wide", 25_000);
        assertEquals("SWITCHING TO Wide... 25 s", s.headline(0));
        assertEquals("SWITCHING TO Wide... 1 s", s.headline(24_500));
        assertEquals("SWITCHING TO Wide... 0 s", s.headline(30_000));
    }

    // The air reverts by itself at the deadline and its beacon says so. If no answer ever comes (the air died
    // mid-switch), the gap stops being "expected" after a grace, so the pilot gets the real NO SIGNAL again.
    @Test public void aSwitchWithNoAnswerStopsExcusingTheGapAfterTheGrace() {
        PresetStatus s = new PresetStatus();
        s.switching("Wide", 25_000);
        assertTrue(s.expectsGap(0));
        assertTrue(s.expectsGap(25_000 + PresetStatus.GAP_GRACE_MS));
        assertFalse(s.expectsGap(25_000 + PresetStatus.GAP_GRACE_MS + 1));
        assertEquals("", s.headline(25_000 + PresetStatus.GAP_GRACE_MS + 1));
        assertTrue(s.switching());                      // still waiting for the air's answer
    }

    @Test public void noGapIsExpectedOnceTheSwitchHasAResult() {
        PresetStatus s = new PresetStatus();
        s.switching("Wide", 25_000);
        s.done("Wide", 10_000);
        assertFalse(s.expectsGap(10_000));
    }

    @Test public void resultShowsForAWhileThenClears() {
        PresetStatus s = new PresetStatus();
        s.switching("Wide", 25_000);
        s.done("Wide", 10_000);
        assertFalse(s.switching());
        assertEquals("Wide ACTIVE", s.headline(10_000));
        assertEquals("", s.headline(10_000 + PresetStatus.RESULT_MS));
    }

    @Test public void headlinesNeverExceedTheLimit() {
        PresetStatus s = new PresetStatus();
        String longLabel = "A-very-long-preset-label-from-the-air";
        s.switching(longLabel, 99_000);
        assertTrue(s.headline(0).length() <= PresetStatus.MAX_HEADLINE);
        s.reverted(longLabel, 0);
        assertTrue(s.headline(0).length() <= PresetStatus.MAX_HEADLINE);
        s.refused("no reply from the air unit after five tries", 0);
        assertTrue(s.headline(0).length() <= PresetStatus.MAX_HEADLINE);
        assertTrue(s.headline(0).startsWith("NOT APPLIED: NO REPLY"));
    }
}
