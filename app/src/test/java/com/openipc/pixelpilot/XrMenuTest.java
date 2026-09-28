package com.openipc.pixelpilot;

import static org.junit.Assert.*;

import com.openipc.videonative.LatencyExperiments;
import com.openipc.xr.PresetCatalog;
import com.openipc.xr.menu.ApplyClass;
import com.openipc.xr.menu.MenuAction;
import com.openipc.xr.menu.MenuItem;
import com.openipc.xr.menu.StatsPages;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.junit.Before;
import org.junit.Test;

/** The XR menu's tree, model and actions (docs/xr/menu-design.md): what it offers, shows and does. */
public class XrMenuTest {
    static final class MapPrefs implements LatencyExperiments.PrefSource {
        final Map<String, Object> m = new HashMap<>();
        @Override public boolean getBoolean(String k, boolean d) { return m.containsKey(k) ? (Boolean) m.get(k) : d; }
        @Override public int getInt(String k, int d) { return m.containsKey(k) ? (Integer) m.get(k) : d; }
        @Override public float getFloat(String k, float d) { return m.containsKey(k) ? (Float) m.get(k) : d; }
        @Override public String getString(String k, String d) { return m.containsKey(k) ? (String) m.get(k) : d; }
    }

    /** Records every effect the actions ask for. */
    static final class Effects implements XrMenuActions.Effects {
        final MapPrefs prefs = new MapPrefs();
        final List<String> log = new ArrayList<>();
        String panel = "detailed";
        @Override public void putBoolean(String k, boolean v) { prefs.m.put(k, v); log.add("put " + k + "=" + v); }
        @Override public void putInt(String k, int v) { prefs.m.put(k, v); log.add("put " + k + "=" + v); }
        @Override public void putFloat(String k, float v) { prefs.m.put(k, v); log.add("put " + k + "=" + v); }
        @Override public void putString(String k, String v) { prefs.m.put(k, v); log.add("put " + k + "=" + v); }
        @Override public void remove(String k) { prefs.m.remove(k); log.add("remove " + k); }
        @Override public void applyLive() { log.add("live"); }
        @Override public void relaunch() { log.add("relaunch"); }
        @Override public void setPanelMode(String mode) { panel = mode; log.add("panel " + mode); }
        @Override public void airApply(String mode, int kbps) { log.add("air mode=" + mode + " kbps=" + kbps); }
        @Override public void airSaveDefault() { log.add("air save"); }
    }

    static final PresetCatalog CATALOG = new PresetCatalog(
            Arrays.asList(new PresetCatalog.Mode("race", "Race", "640x480@167", "33x44", "26.7-32.0"),
                    new PresetCatalog.Mode("wide", "Wide", "1920x1080@90>848x480", "99x98", "35.3-41.6")),
            Arrays.asList(new PresetCatalog.Quality(2000, "0"), new PresetCatalog.Quality(4000, "1.7")),
            "race", "race", 2000);

    MenuItem tree;
    Effects fx;
    PresetCatalog catalog;
    XrMenuModel model;
    XrMenuActions actions;

    @Before public void setUp() {
        tree = XrMenuTree.build();
        fx = new Effects();
        catalog = null;
        model = new XrMenuModel(() -> LatencyExperiments.from(fx.prefs, true), () -> catalog, () -> fx.panel);
        actions = new XrMenuActions(fx);
    }

    MenuAction act(MenuAction.Type type, String id, String value) {
        return new MenuAction(type, tree.find(id), value);
    }

    @Test public void theTreeOffersEveryLeverAndTheStatsPages() {
        for (String id : new String[]{LatencyExperiments.KEY_FEED_INCOMPLETE_FRAMES,
                LatencyExperiments.KEY_REQUEST_IDR_ON_LOSS, LatencyExperiments.KEY_IDR_MIN_INTERVAL_MS,
                LatencyExperiments.KEY_FREEZE_UNTIL_IDR, LatencyExperiments.KEY_RTP_TIGHT_REORDER,
                LatencyExperiments.KEY_LOW_LATENCY_DECODER, LatencyExperiments.KEY_DEC_PICTURE_ORDER,
                LatencyExperiments.KEY_DEC_OPERATING_RATE, LatencyExperiments.KEY_DEC_PREFER_LOW_LATENCY_COMPONENT,
                LatencyExperiments.KEY_AU_AGGREGATION, LatencyExperiments.KEY_XR_REFRESH_HZ,
                LatencyExperiments.KEY_XR_FOV_DEG, LatencyExperiments.KEY_XR_LAYER_SHAPE,
                LatencyExperiments.KEY_XR_FLIP_VERTICAL, LatencyExperiments.KEY_XR_USE_TIMESTAMPS,
                LatencyExperiments.KEY_XR_PERF_SUSTAINED_HIGH, LatencyExperiments.KEY_XR_THREAD_HINTS,
                XrMenuTree.AIR_MODE, XrMenuTree.AIR_QUALITY, XrMenuTree.PANEL_DETAIL}) {
            assertNotNull(id, tree.find(id));
        }
        for (String page : StatsPages.PAGES) assertNotNull(page, tree.find(page));
    }

    @Test public void everyFolderFitsSevenLines() {
        check(tree);
    }

    private void check(MenuItem folder) {
        assertTrue(folder.id + " has " + folder.children.size(), folder.children.size() <= 7);
        for (MenuItem c : folder.children) if (c.kind == MenuItem.Kind.FOLDER) check(c);
    }

    @Test public void streamLeversAreLiveDecoderKeysRelaunch() {
        assertEquals(ApplyClass.LIVE, tree.find(LatencyExperiments.KEY_FREEZE_UNTIL_IDR).apply);
        assertEquals(ApplyClass.RELAUNCH, tree.find(LatencyExperiments.KEY_DEC_PICTURE_ORDER).apply);
        assertEquals(ApplyClass.RELAUNCH, tree.find(LatencyExperiments.KEY_XR_REFRESH_HZ).apply);
        assertEquals(ApplyClass.LIVE, tree.find(LatencyExperiments.KEY_XR_FOV_DEG).apply);
        assertEquals(ApplyClass.AIR, tree.find(XrMenuTree.AIR_MODE).apply);
    }

    @Test public void theModelShowsTheLeversDefaultsFromLatencyExperiments() {
        assertEquals("false", model.value(LatencyExperiments.KEY_FEED_INCOMPLETE_FRAMES));
        assertEquals("true", model.value(LatencyExperiments.KEY_RTP_TIGHT_REORDER));
        assertEquals("default", model.value(LatencyExperiments.KEY_IDR_MIN_INTERVAL_MS));
        assertEquals("60", model.value(LatencyExperiments.KEY_XR_FOV_DEG));
        assertEquals("quad", model.value(LatencyExperiments.KEY_XR_LAYER_SHAPE));
        assertTrue(model.choices(LatencyExperiments.KEY_XR_REFRESH_HZ).contains("120"));
        assertEquals("detailed", model.value(XrMenuTree.PANEL_DETAIL));
    }

    @Test public void airLinesNeedTheAirsListAndRadioLinesAreGreyedOut() {
        assertFalse(model.available(XrMenuTree.AIR_MODE));
        catalog = CATALOG;
        assertTrue(model.available(XrMenuTree.AIR_MODE));
        assertEquals("race", model.value(XrMenuTree.AIR_MODE));
        assertEquals(Arrays.asList("race", "wide"), model.choices(XrMenuTree.AIR_MODE));
        assertEquals("2000", model.value(XrMenuTree.AIR_QUALITY));
        assertFalse(model.available(XrMenuTree.AIR_CODEC));
        assertFalse(model.available(XrMenuTree.AIR_MCS));
        assertTrue(model.available(LatencyExperiments.KEY_FREEZE_UNTIL_IDR));
    }

    @Test public void aLiveLeverIsWrittenThenAppliedLive() {
        actions.run(act(MenuAction.Type.SET, LatencyExperiments.KEY_FREEZE_UNTIL_IDR, "true"));
        assertEquals(Arrays.asList("put freeze_until_idr=true", "live"), fx.log);
        assertTrue(LatencyExperiments.from(fx.prefs).freezeUntilIdr);
    }

    @Test public void aDecoderKeyIsWrittenThenRelaunches() {
        actions.run(act(MenuAction.Type.SET, LatencyExperiments.KEY_XR_REFRESH_HZ, "120"));
        assertEquals(Arrays.asList("put xr_refresh_hz=120", "relaunch"), fx.log);
    }

    @Test public void typedWritesMatchWhatLatencyExperimentsReads() {
        actions.run(act(MenuAction.Type.SET, LatencyExperiments.KEY_XR_FOV_DEG, "80"));
        actions.run(act(MenuAction.Type.SET, LatencyExperiments.KEY_XR_LAYER_SHAPE, "cylinder"));
        actions.run(act(MenuAction.Type.SET, LatencyExperiments.KEY_IDR_MIN_INTERVAL_MS, "500"));
        LatencyExperiments e = LatencyExperiments.from(fx.prefs);
        assertEquals(80f, e.xrFovDeg, 0f);
        assertEquals(LatencyExperiments.LayerShape.CYLINDER, e.xrLayerShape);
        assertEquals(500, e.idrMinIntervalMs);
        actions.run(act(MenuAction.Type.SET, LatencyExperiments.KEY_IDR_MIN_INTERVAL_MS, "default"));
        assertEquals(-1, LatencyExperiments.from(fx.prefs).idrMinIntervalMs);
    }

    @Test public void thePanelModeIsSetWithoutAPref() {
        actions.run(act(MenuAction.Type.SET, XrMenuTree.PANEL_DETAIL, "compact"));
        assertEquals(Arrays.asList("panel compact"), fx.log);
    }

    @Test public void airActionsGoToTheVmodeSession() {
        actions.run(act(MenuAction.Type.APPLY_AIR, XrMenuTree.AIR_MODE, "wide"));
        actions.run(act(MenuAction.Type.APPLY_AIR, XrMenuTree.AIR_QUALITY, "4000"));
        actions.run(act(MenuAction.Type.SAVE_AIR_DEFAULT, XrMenuTree.AIR_MODE, "race"));
        assertEquals(Arrays.asList("air mode=wide kbps=0", "air mode=null kbps=4000", "air save"), fx.log);
    }

    @Test public void resetRemovesEveryQuestKeyTheMenuOwnsThenRelaunches() {
        actions.run(act(MenuAction.Type.SET, LatencyExperiments.KEY_FEED_INCOMPLETE_FRAMES, "true"));
        fx.log.clear();
        actions.run(act(MenuAction.Type.RUN, XrMenuTree.RESET_QUEST, null));
        assertTrue(fx.log.contains("remove " + LatencyExperiments.KEY_FEED_INCOMPLETE_FRAMES));
        assertTrue(fx.log.contains("remove " + LatencyExperiments.KEY_XR_REFRESH_HZ));
        assertEquals("relaunch", fx.log.get(fx.log.size() - 1));
        assertFalse(fx.prefs.m.containsKey(LatencyExperiments.KEY_FEED_INCOMPLETE_FRAMES));
    }
}
