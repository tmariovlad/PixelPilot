package com.openipc.xr;

import static org.junit.Assert.*;
import org.junit.Test;

public class RefreshWatchTest {
    @Test public void firstReportedRateIsLoggedOnce() {
        RefreshWatch w = new RefreshWatch();
        assertEquals("XR refresh applied 120 Hz (requested 120)", w.onSample(120.00001f, 120f));
        assertNull(w.onSample(120.00001f, 120f));
    }

    @Test public void unreportedRateLogsNothing() {
        RefreshWatch w = new RefreshWatch();
        assertNull(w.onSample(-1f, 120f));
        assertEquals("XR refresh applied 120 Hz (requested 120)", w.onSample(120f, 120f));
    }

    @Test public void aThermalDropIsLoggedAndFlagged() {
        RefreshWatch w = new RefreshWatch();
        w.onSample(120f, 120f);
        assertEquals("XR refresh 120 -> 72 Hz (requested 120) BELOW REQUEST", w.onSample(72f, 120f));
        assertNull(w.onSample(72f, 120f));
        assertEquals("XR refresh 72 -> 120 Hz (requested 120)", w.onSample(120f, 120f));
    }

    @Test public void aRateSeenBeforeTheRequestSaysSo() {
        // On the headset the runtime reports 90 Hz before the app's request is applied (logcat 2026-09-28 11:07:48).
        RefreshWatch w = new RefreshWatch();
        assertEquals("XR refresh applied 90 Hz (not requested yet)", w.onSample(90f, -1f));
        assertEquals("XR refresh 90 -> 120 Hz (requested 120)", w.onSample(120f, 120f));
    }

    @Test public void subHertzJitterIsNotAChange() {
        RefreshWatch w = new RefreshWatch();
        w.onSample(120f, 120f);
        assertNull(w.onSample(119.7f, 120f));
    }

    @Test public void hudSuffixOnlyWhenBelowTheRequest() {
        assertEquals("", RefreshWatch.hudSuffix(120.00001f, 120f));
        assertEquals("", RefreshWatch.hudSuffix(119.7f, 120f));
        assertEquals(" BELOW REQUEST", RefreshWatch.hudSuffix(72f, 120f));
        assertEquals("", RefreshWatch.hudSuffix(-1f, 120f));   // not reported: no claim either way
        assertEquals("", RefreshWatch.hudSuffix(90f, 90f));
    }
}
