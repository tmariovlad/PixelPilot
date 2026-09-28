package com.openipc.wfbngrtl8812;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.util.HashMap;
import java.util.Map;
import org.junit.Test;

public class RxDiagPrefsTest {
    @Test
    public void absentPrefsMeanEverythingOff() {
        RxDiagPrefs d = RxDiagPrefs.fromPrefs(new HashMap<>());
        assertEquals(0, d.ringMs);
        assertFalse(d.keepCorrupted);
        assertEquals(RxDiagPrefs.MODE_ASYNC, d.rxMode);
        assertFalse(d.enabled());
    }

    @Test
    public void readsTheThreeKeys() {
        Map<String, Object> p = new HashMap<>();
        p.put(RxDiagPrefs.KEY_RING_MS, 100);
        p.put(RxDiagPrefs.KEY_KEEP_CORRUPTED, true);
        p.put(RxDiagPrefs.KEY_MODE, "spsc");
        RxDiagPrefs d = RxDiagPrefs.fromPrefs(p);
        assertEquals(100, d.ringMs);
        assertTrue(d.keepCorrupted);
        assertEquals(RxDiagPrefs.MODE_SPSC, d.rxMode);
        assertTrue(d.enabled());
    }

    @Test
    public void reorderModeAndUnknownModeFallsBackToAsync() {
        Map<String, Object> p = new HashMap<>();
        p.put(RxDiagPrefs.KEY_MODE, "reorder");
        assertEquals(RxDiagPrefs.MODE_REORDER, RxDiagPrefs.fromPrefs(p).rxMode);
        p.put(RxDiagPrefs.KEY_MODE, "turbo");
        assertEquals(RxDiagPrefs.MODE_ASYNC, RxDiagPrefs.fromPrefs(p).rxMode);
    }

    @Test
    public void ringMsIsClampedAndWrongTypesAreIgnored() {
        Map<String, Object> p = new HashMap<>();
        p.put(RxDiagPrefs.KEY_RING_MS, -5);
        assertEquals(0, RxDiagPrefs.fromPrefs(p).ringMs);
        p.put(RxDiagPrefs.KEY_RING_MS, 60000);
        assertEquals(RxDiagPrefs.MAX_RING_MS, RxDiagPrefs.fromPrefs(p).ringMs);
        p.put(RxDiagPrefs.KEY_RING_MS, "100");            // a string where an int belongs: ignored, off
        p.put(RxDiagPrefs.KEY_KEEP_CORRUPTED, "yes");     // same for the boolean
        RxDiagPrefs d = RxDiagPrefs.fromPrefs(p);
        assertEquals(0, d.ringMs);
        assertFalse(d.keepCorrupted);
    }
}
