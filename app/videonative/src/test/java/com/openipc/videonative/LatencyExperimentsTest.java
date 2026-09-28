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

    // The reorder hold after a lost packet made the next frames ~9 ms late at 2 % loss (docs/xr/g2g-budget.md,
    // "The Quest's parse time and the reorder hold"); tight is the default everywhere, the upstream bound stays
    // selectable for an A/B and shows in the summary.
    @Test public void tightReorderIsTheDefaultAndCanBeTurnedOff() {
        assertTrue(LatencyExperiments.from(new MapPrefs()).rtpTightReorder);
        assertTrue(LatencyExperiments.from(new MapPrefs(), true).rtpTightReorder);
        LatencyExperiments off = LatencyExperiments.from(
                new MapPrefs().put(LatencyExperiments.KEY_RTP_TIGHT_REORDER, false));
        assertFalse(off.rtpTightReorder);
        assertTrue(off.summary(), off.summary().startsWith("LL RQ20 |"));
    }

    // A frame with a lost RTP packet is dropped whole by the depacketizer (docs/xr/link-envelope.md, "frame fate").
    // Feeding it incomplete is an A/B lever, off by default; it shows in the summary when on.
    @Test public void feedIncompleteFramesIsOffByDefaultAndShowsWhenOn() {
        assertFalse(LatencyExperiments.from(new MapPrefs()).feedIncompleteFrames);
        assertFalse(LatencyExperiments.from(new MapPrefs(), true).feedIncompleteFrames);
        LatencyExperiments on = LatencyExperiments.from(
                new MapPrefs().put(LatencyExperiments.KEY_FEED_INCOMPLETE_FRAMES, true));
        assertTrue(on.feedIncompleteFrames);
        assertTrue(on.summary(), on.summary().contains("FIF"));
        assertFalse(LatencyExperiments.from(new MapPrefs()).summary().contains("FIF"));
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

    // Measured on Quest 2 (docs/xr/decoder-levers.md): max operating rate halves the decode time, so it is the
    // default there; phones keep it off (moonlight saw Qualcomm decoders fail with it).
    @Test public void operatingRateDefaultsOnOnlyForMetaHeadsets() {
        assertTrue(LatencyExperiments.from(new MapPrefs(), true).decOperatingRate);
        assertFalse(LatencyExperiments.from(new MapPrefs(), false).decOperatingRate);
        assertFalse(LatencyExperiments.from(new MapPrefs()).decOperatingRate);
    }

    // Re-measured on clean streams (docs/xr/decoder-levers.md): low-latency keys + operating rate beat operating
    // rate alone on H.264 720p, H.265 720p and H.265 1080p, so Meta headsets keep the keys on too.
    @Test public void lowLatencyKeysDefaultOnForMetaHeadsets() {
        assertTrue(LatencyExperiments.from(new MapPrefs(), true).lowLatencyDecoder);
        assertTrue(LatencyExperiments.from(new MapPrefs(), false).lowLatencyDecoder);
        MapPrefs off = new MapPrefs().put(LatencyExperiments.KEY_LOW_LATENCY_DECODER, false);
        assertFalse(LatencyExperiments.from(off, true).lowLatencyDecoder);
    }

    // Real OpenIPC stream on Quest 2 (docs/xr/real-link.md, "First real link"): without decode-order output the
    // OMX decoder holds ~16 frames (96 ms at 166 fps) because the SPS does not rule out reordering.
    @Test public void pictureOrderDefaultsOnOnlyForMetaHeadsets() {
        assertTrue(LatencyExperiments.from(new MapPrefs(), true).decPictureOrder);
        assertFalse(LatencyExperiments.from(new MapPrefs(), false).decPictureOrder);
        MapPrefs off = new MapPrefs().put(LatencyExperiments.KEY_DEC_PICTURE_ORDER, false);
        assertFalse(LatencyExperiments.from(off, true).decPictureOrder);
    }

    // Headsets start straight in XR (user request 2026-09-27); phones keep the 2D screen.
    @Test public void xrAutostartDefaultsOnOnlyForMetaHeadsets() {
        assertTrue(LatencyExperiments.from(new MapPrefs(), true).xrAutostart);
        assertFalse(LatencyExperiments.from(new MapPrefs(), false).xrAutostart);
        MapPrefs off = new MapPrefs().put(LatencyExperiments.KEY_XR_AUTOSTART, false);
        assertFalse(LatencyExperiments.from(off, true).xrAutostart);
    }

    @Test public void phaseReportIsOffAndLatchOffsetCalibratedByDefault() {
        LatencyExperiments e = LatencyExperiments.from(new MapPrefs(), true);
        assertEquals("", e.xrPhaseReport);
        assertEquals(LatencyExperiments.DEFAULT_LATCH_TO_DISPLAY_US, e.xrLatchToDisplayUs);
        MapPrefs p = new MapPrefs().put(LatencyExperiments.KEY_XR_PHASE_REPORT, "10.0.0.2:5610")
                .put(LatencyExperiments.KEY_XR_LATCH_TO_DISPLAY_US, 1234);
        e = LatencyExperiments.from(p, true);
        assertEquals("10.0.0.2:5610", e.xrPhaseReport);
        assertEquals(1234, e.xrLatchToDisplayUs);
    }

    @Test public void storedOperatingRateOverridesTheDeviceDefault() {
        MapPrefs off = new MapPrefs().put(LatencyExperiments.KEY_DEC_OPERATING_RATE, false);
        assertFalse(LatencyExperiments.from(off, true).decOperatingRate);
    }

    @Test public void debugKeyMaskDefaultsToAllKeys() {
        assertEquals(-1, LatencyExperiments.from(new MapPrefs()).decDebugKeyMask);
        assertEquals(0x20, LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_DEC_DEBUG_KEY_MASK, 0x20)).decDebugKeyMask);
    }

    @Test public void decoderComponentDefaultsToEmpty() {
        assertEquals("", LatencyExperiments.from(new MapPrefs()).decComponent);
        assertEquals("c2.qti.hevc.decoder",
                LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_DEC_COMPONENT, "c2.qti.hevc.decoder")).decComponent);
    }

    @Test public void metaHeadsetDetection() {
        assertTrue(LatencyExperiments.isMetaHeadset("Oculus"));
        assertTrue(LatencyExperiments.isMetaHeadset("Meta"));
        assertFalse(LatencyExperiments.isMetaHeadset("samsung"));
        assertFalse(LatencyExperiments.isMetaHeadset(null));
    }

    // Final review Minor 3: a wrong-typed stored pref must fall back to the default, not crash.
    @Test public void wrongTypedPrefsFallBackToDefaults() {
        LatencyExperiments e = LatencyExperiments.from(new WrongTypePrefs());
        assertTrue(e.lowLatencyDecoder);
        assertEquals(LatencyExperiments.DEFAULT_REFRESH_HZ, e.xrRefreshHz);
        assertEquals(LatencyExperiments.DEFAULT_FOV_DEG, e.xrFovDeg, 0f);
        assertEquals(LatencyExperiments.LayerShape.QUAD, e.xrLayerShape);
    }

    @Test public void sameXrStartComparesOnlyXrLevers() {
        LatencyExperiments a = LatencyExperiments.from(new MapPrefs());
        assertTrue(a.sameXrStart(LatencyExperiments.from(new MapPrefs())));
        // a decoder lever alone does not need an XR restart (the menu restarts the process for those)
        assertTrue(a.sameXrStart(LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_DEC_PICTURE_ORDER, true))));
        assertFalse(a.sameXrStart(LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_XR_FOV_DEG, 80f))));
        assertFalse(a.sameXrStart(LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_XR_REFRESH_HZ, 90))));
    }
}
