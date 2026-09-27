package com.openipc.xr;

import static org.junit.Assert.*;

import org.junit.Test;

public class PanelModeTest {
    private static final String[] LINES = {"link", "telemetry", "video", "decode", "status", "phase"};

    @Test public void detailedByDefault() {
        assertArrayEquals(LINES, new PanelMode().select(LINES));
    }

    @Test public void detailPressTogglesCompact() {
        PanelMode m = new PanelMode();
        m.apply(XrBridge.INPUT_PANEL_DETAIL);
        assertArrayEquals(new String[]{"link", "telemetry", "video"}, m.select(LINES));
        m.apply(XrBridge.INPUT_PANEL_DETAIL);
        assertArrayEquals(LINES, m.select(LINES));
    }

    @Test public void visibilityPressHidesAndShows() {
        PanelMode m = new PanelMode();
        m.apply(XrBridge.INPUT_PANEL_VISIBILITY);
        assertEquals(0, m.select(LINES).length);
        m.apply(XrBridge.INPUT_PANEL_VISIBILITY);
        assertArrayEquals(LINES, m.select(LINES));
    }

    @Test public void detailPressOnAHiddenPanelShowsItAgainWithoutChangingDetail() {
        PanelMode m = new PanelMode();
        m.apply(XrBridge.INPUT_PANEL_VISIBILITY);
        m.apply(XrBridge.INPUT_PANEL_DETAIL);
        assertFalse(m.hidden());
        assertFalse(m.compact());
    }

    @Test public void compactNeverPadsShortInput() {
        PanelMode m = new PanelMode();
        m.apply(XrBridge.INPUT_PANEL_DETAIL);
        assertArrayEquals(new String[]{"link"}, m.select(new String[]{"link"}));
    }

    @Test public void noEventsChangeNothing() {
        PanelMode m = new PanelMode();
        m.apply(0);
        assertArrayEquals(LINES, m.select(LINES));
    }
}
