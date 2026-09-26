package com.openipc.videonative;

import static org.junit.Assert.*;

import java.util.HashMap;
import java.util.Map;
import org.junit.Test;

public class LatencyExperimentsTest {
    private static final class MapPrefs implements LatencyExperiments.PrefSource {
        final Map<String, Object> m = new HashMap<>();
        MapPrefs put(String k, Object v) { m.put(k, v); return this; }
        public boolean getBoolean(String k, boolean d) { Object v = m.get(k); return v instanceof Boolean ? (Boolean) v : d; }
        public int getInt(String k, int d) { Object v = m.get(k); return v instanceof Integer ? (Integer) v : d; }
        public float getFloat(String k, float d) { Object v = m.get(k); return v instanceof Float ? (Float) v : d; }
        public String getString(String k, String d) { Object v = m.get(k); return v instanceof String ? (String) v : d; }
    }

    @Test public void defaultsMatchSpec() {
        LatencyExperiments e = LatencyExperiments.from(new MapPrefs());
        assertTrue(e.lowLatencyDecoder);
        assertFalse(e.decPictureOrder);
        assertFalse(e.decOperatingRate);
        assertFalse(e.decPreferLowLatencyComponent);
        assertFalse(e.auAggregation);
        assertEquals(120, e.xrRefreshHz);
        assertFalse(e.xrUseTimestamps);
        assertEquals(LatencyExperiments.LayerShape.QUAD, e.xrLayerShape);
        assertTrue(e.xrPerfSustainedHigh);
        assertEquals(60f, e.xrFovDeg, 0f);
        assertTrue(e.xrFlipVertical);
        assertTrue(e.xrThreadHints);
    }

    @Test public void storedValuesAreRead() {
        MapPrefs p = new MapPrefs()
                .put(LatencyExperiments.KEY_LOW_LATENCY_DECODER, false)
                .put(LatencyExperiments.KEY_DEC_PICTURE_ORDER, true)
                .put(LatencyExperiments.KEY_AU_AGGREGATION, true)
                .put(LatencyExperiments.KEY_XR_REFRESH_HZ, 90)
                .put(LatencyExperiments.KEY_XR_LAYER_SHAPE, "cylinder")
                .put(LatencyExperiments.KEY_XR_FOV_DEG, 80f);
        LatencyExperiments e = LatencyExperiments.from(p);
        assertFalse(e.lowLatencyDecoder);
        assertTrue(e.decPictureOrder);
        assertTrue(e.auAggregation);
        assertEquals(90, e.xrRefreshHz);
        assertEquals(LatencyExperiments.LayerShape.CYLINDER, e.xrLayerShape);
        assertEquals(80f, e.xrFovDeg, 0f);
    }

    @Test public void unsupportedRefreshFallsBackToDefault() {
        assertEquals(120, LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_XR_REFRESH_HZ, 144)).xrRefreshHz);
        assertEquals(120, LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_XR_REFRESH_HZ, 0)).xrRefreshHz);
    }

    @Test public void fovIsClampedAndNaNIsDefault() {
        assertEquals(LatencyExperiments.MAX_FOV_DEG, LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_XR_FOV_DEG, 500f)).xrFovDeg, 0f);
        assertEquals(LatencyExperiments.MIN_FOV_DEG, LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_XR_FOV_DEG, 1f)).xrFovDeg, 0f);
        assertEquals(LatencyExperiments.DEFAULT_FOV_DEG, LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_XR_FOV_DEG, Float.NaN)).xrFovDeg, 0f);
    }

    @Test public void unknownShapeIsQuad() {
        assertEquals(LatencyExperiments.LayerShape.QUAD, LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_XR_LAYER_SHAPE, "sphere")).xrLayerShape);
    }

    @Test public void summaryListsOnlyEnabledLevers() {
        assertEquals("LL | 120Hz quad perf hints flip", LatencyExperiments.from(new MapPrefs()).summary());
        MapPrefs p = new MapPrefs().put(LatencyExperiments.KEY_LOW_LATENCY_DECODER, false)
                .put(LatencyExperiments.KEY_XR_PERF_SUSTAINED_HIGH, false)
                .put(LatencyExperiments.KEY_XR_THREAD_HINTS, false)
                .put(LatencyExperiments.KEY_XR_FLIP_VERTICAL, false);
        assertEquals("stock | 120Hz quad", LatencyExperiments.from(p).summary());
    }

    /** Behaves like SharedPreferences when a key was stored with another type. */
    private static final class WrongTypePrefs implements LatencyExperiments.PrefSource {
        public boolean getBoolean(String k, boolean d) { throw new ClassCastException("Integer cannot be cast to Boolean"); }
        public int getInt(String k, int d) { throw new ClassCastException("String cannot be cast to Integer"); }
        public float getFloat(String k, float d) { throw new ClassCastException("Boolean cannot be cast to Float"); }
        public String getString(String k, String d) { throw new ClassCastException("Float cannot be cast to String"); }
    }

    // Final review Minor 3: a wrong-typed stored pref must fall back to the default, not crash.
    @Test public void wrongTypedPrefsFallBackToDefaults() {
        LatencyExperiments e = LatencyExperiments.from(new WrongTypePrefs());
        assertTrue(e.lowLatencyDecoder);
        assertEquals(LatencyExperiments.DEFAULT_REFRESH_HZ, e.xrRefreshHz);
        assertEquals(LatencyExperiments.DEFAULT_FOV_DEG, e.xrFovDeg, 0f);
        assertEquals(LatencyExperiments.LayerShape.QUAD, e.xrLayerShape);
    }
}
