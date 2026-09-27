package com.openipc.xr;

import static org.junit.Assert.*;

import java.util.Arrays;

import org.junit.Test;

public class PresetMenuTest {
    private static final int LEFT = XrBridge.INPUT_STICK_LEFT, RIGHT = XrBridge.INPUT_STICK_RIGHT;
    private static final int UP = XrBridge.INPUT_STICK_UP;
    private static final int PRESS = XrBridge.INPUT_STICK_PRESS, RELEASE = XrBridge.INPUT_STICK_RELEASE;

    static PresetCatalog catalog() {
        return new PresetCatalog(Arrays.asList(
                new PresetCatalog.Mode("race", "Race", "640x480@167", "33x44", "26.7-32.0"),
                new PresetCatalog.Mode("balanced", "Balanced", "1280x720@119", "66x66", "33.0-38.3"),
                new PresetCatalog.Mode("wide", "Wide", "1920x1080@90>848x480", "99x98", "35.3-41.6")),
                Arrays.asList(new PresetCatalog.Quality(2000, "0"), new PresetCatalog.Quality(4000, "1.7"),
                        new PresetCatalog.Quality(6000, "3.1")),
                "race", "race", 2000);
    }

    private static PresetMenu menu() {
        PresetMenu m = new PresetMenu();
        m.setCatalog(catalog());
        return m;
    }

    @Test public void firstFlickOnlyOpens() {
        PresetMenu m = menu();
        assertNull(m.update(RIGHT, 0));
        assertTrue(m.isOpen());
        assertTrue(m.lines(false, 0)[0].startsWith("MODE < Race >"));
    }

    @Test public void holdOneSecondAppliesTheHighlightedMode() {
        PresetMenu m = menu();
        m.update(RIGHT, 0);
        m.update(RIGHT, 100);                     // Balanced
        m.update(RIGHT, 200);                     // Wide
        assertNull(m.update(PRESS, 300));
        assertNull(m.update(0, 1200));            // 0.9 s: not yet
        PresetMenu.Action a = m.update(0, 1300);
        assertNotNull(a);
        assertEquals("wide", a.mode);
        assertEquals(0, a.kbps);                  // quality unchanged
        assertFalse(a.saveDefault);
        assertFalse(m.isOpen());
        assertNull(m.update(0, 5000));            // the same hold never fires twice
    }

    @Test public void releaseBeforeTheHoldDoesNothing() {
        PresetMenu m = menu();
        m.update(RIGHT, 0);
        m.update(RIGHT, 100);
        m.update(PRESS, 200);
        assertNull(m.update(RELEASE, 900));
        assertNull(m.update(0, 2000));
        assertTrue(m.isOpen());
    }

    @Test public void qualityOnlyChangeSendsOnlyKbps() {
        PresetMenu m = menu();
        m.update(UP, 0);                          // opens
        m.update(UP, 100);                        // 4 Mbit
        m.update(PRESS, 200);
        PresetMenu.Action a = m.update(0, 1200);
        assertNull(a.mode);
        assertEquals(4000, a.kbps);
    }

    @Test public void holdThreeSecondsOnTheActiveChoiceSavesDefault() {
        PresetMenu m = menu();
        m.update(RIGHT, 0);                       // opens on the active choice
        m.update(PRESS, 100);
        assertNull(m.update(0, 1100));            // nothing to apply at 1 s
        PresetMenu.Action a = m.update(0, 3100);
        assertTrue(a.saveDefault);
    }

    @Test public void closesAfterIdleButNotWhileHeld() {
        PresetMenu m = menu();
        m.update(RIGHT, 0);
        m.update(0, PresetMenu.IDLE_CLOSE_MS - 1);
        assertTrue(m.isOpen());
        m.update(0, PresetMenu.IDLE_CLOSE_MS);
        assertFalse(m.isOpen());
    }

    @Test public void visibilityPressClosesTheMenuInsteadOfHidingThePanel() {
        PresetMenu m = menu();
        m.update(RIGHT, 0);
        int rest = m.passThrough(XrBridge.INPUT_PANEL_VISIBILITY);
        assertEquals(0, rest);
        m.update(XrBridge.INPUT_PANEL_VISIBILITY, 100);
        assertFalse(m.isOpen());
        assertEquals(XrBridge.INPUT_PANEL_VISIBILITY, m.passThrough(XrBridge.INPUT_PANEL_VISIBILITY));
    }

    @Test public void highlightStaysAtTheEnds() {
        PresetMenu m = menu();
        m.update(LEFT, 0);
        m.update(LEFT, 100);                      // already at Race
        assertTrue(m.lines(false, 100)[0].startsWith("MODE < Race >"));
    }

    @Test public void modeChangeShowsTheSwitchWarningAndArmed() {
        PresetMenu m = menu();
        m.update(RIGHT, 0);
        m.update(RIGHT, 100);
        String hint = m.lines(true, 100)[3];
        assertTrue(hint.contains(PresetMenu.SWITCH_WARNING));
        assertTrue(hint.endsWith("ARMED"));
    }

    @Test public void withoutAListTheMenuSaysSoAndAppliesNothing() {
        PresetMenu m = new PresetMenu();
        m.update(RIGHT, 0);
        m.update(PRESS, 100);
        assertNull(m.update(0, 5000));
        assertEquals(1, m.lines(false, 0).length);
    }

    @Test public void menuLinesFitThePanel() {
        PresetMenu m = new PresetMenu();
        m.setCatalog(new PresetCatalog(Arrays.asList(
                new PresetCatalog.Mode("balanced-lite", "Balanced-lite", "1280x720@119.2>848x480", "66x66", "31.3-37.6")),
                Arrays.asList(new PresetCatalog.Quality(6000, "3.1")), "x", "x", 2000));
        m.update(RIGHT, 0);
        for (String line : m.lines(true, 0)) assertTrue(line, line.length() <= 60);
    }

    @Test public void encodeSizeIsTheScaledSizeWhenThereIsOne() {
        assertArrayEquals(new int[]{848, 480}, catalog().modes.get(2).encodeSize());
        assertArrayEquals(new int[]{640, 480}, catalog().modes.get(0).encodeSize());
    }
}
