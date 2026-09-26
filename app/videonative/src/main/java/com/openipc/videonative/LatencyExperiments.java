package com.openipc.videonative;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;

/**
 * Single source of truth for every latency lever: pref keys, defaults and validation.
 * The 2D activity, the XR activity and the decoder all read it; nothing else names these keys.
 * An instance is an immutable snapshot of the prefs at load time.
 */
public final class LatencyExperiments {
    public static final String PREFS_NAME = "general";

    public static final String KEY_LOW_LATENCY_DECODER = "low_latency_decoder";
    public static final String KEY_DEC_PICTURE_ORDER = "dec_picture_order";
    public static final String KEY_DEC_OPERATING_RATE = "dec_operating_rate";
    public static final String KEY_DEC_PREFER_LOW_LATENCY_COMPONENT = "dec_prefer_low_latency_component";
    public static final String KEY_AU_AGGREGATION = "au_aggregation";
    /** Debug: bitmask over the individual decoder keys (DecoderLevers.h DecoderKey); -1 = all. */
    public static final String KEY_DEC_DEBUG_KEY_MASK = "dec_debug_key_mask";
    /** Debug: force a decoder component by name (e.g. "c2.qti.hevc.decoder"); "" = default. */
    public static final String KEY_DEC_COMPONENT = "dec_component";
    public static final String KEY_XR_REFRESH_HZ = "xr_refresh_hz";
    public static final String KEY_XR_USE_TIMESTAMPS = "xr_use_timestamps";
    public static final String KEY_XR_LAYER_SHAPE = "xr_layer_shape";
    public static final String KEY_XR_PERF_SUSTAINED_HIGH = "xr_perf_sustained_high";
    public static final String KEY_XR_FOV_DEG = "xr_fov_deg";
    public static final String KEY_XR_FLIP_VERTICAL = "xr_flip_vertical";
    public static final String KEY_XR_THREAD_HINTS = "xr_thread_hints";
    /** "host:port" that receives compositor-phase reports (XR); "" = off. */
    public static final String KEY_XR_PHASE_REPORT = "xr_phase_report";
    /** predictedDisplayTime minus the compositor latch, in us (device constant, calibrated). */
    public static final String KEY_XR_LATCH_TO_DISPLAY_US = "xr_latch_to_display_us";

    /** Refresh rates Quest 2 offers to OpenXR apps (60 Hz is media-only). */
    public static final int[] SUPPORTED_REFRESH_HZ = {72, 80, 90, 120};
    public static final int DEFAULT_REFRESH_HZ = 120;
    public static final float DEFAULT_FOV_DEG = 60f;
    public static final float MIN_FOV_DEG = 20f;
    public static final float MAX_FOV_DEG = 110f;
    /** Quest 2 @120 Hz, calibrated with a Perfetto trace (docs/xr-quest.md, "Phase lock"). */
    public static final int DEFAULT_LATCH_TO_DISPLAY_US = 3407;

    public enum LayerShape {
        QUAD, CYLINDER;

        static LayerShape parse(String value) {
            return "cylinder".equalsIgnoreCase(value) ? CYLINDER : QUAD;
        }

        public String prefValue() {
            return this == CYLINDER ? "cylinder" : "quad";
        }
    }

    /** Read-only key/value source, so the parsing is testable without Android. */
    public interface PrefSource {
        boolean getBoolean(String key, boolean def);
        int getInt(String key, int def);
        float getFloat(String key, float def);
        String getString(String key, String def);
    }

    public final boolean lowLatencyDecoder;
    public final boolean decPictureOrder;
    public final boolean decOperatingRate;
    public final boolean decPreferLowLatencyComponent;
    public final boolean auAggregation;
    public final int decDebugKeyMask;
    public final String decComponent;
    public final int xrRefreshHz;
    public final boolean xrUseTimestamps;
    public final LayerShape xrLayerShape;
    public final boolean xrPerfSustainedHigh;
    public final float xrFovDeg;
    public final boolean xrFlipVertical;
    public final boolean xrThreadHints;
    public final String xrPhaseReport;
    public final int xrLatchToDisplayUs;

    private LatencyExperiments(PrefSource p, boolean metaHeadset) {
        // Quest 2, clean streams (docs/xr-quest.md): low-latency keys + operating rate is the fastest
        // combination on every stream measured, so the upstream default holds on headsets too.
        lowLatencyDecoder = p.getBoolean(KEY_LOW_LATENCY_DECODER, true);
        // Real OpenIPC (waybeam) stream on Quest 2 (docs/xr-quest.md, "First real link"): without decode-order
        // output OMX.qcom holds ~16 frames, 96 ms at 166 fps -> 1.4 ms with it, N=3. FPV encoders send no
        // B-frames, so decode order is display order. Phones keep the upstream default (not measured).
        decPictureOrder = p.getBoolean(KEY_DEC_PICTURE_ORDER, metaHeadset);
        // Quest 2 measurement (docs/xr-quest.md): decode 10.15 -> 4.99 ms, N=3. Phones keep it off:
        // some Qualcomm decoders fail with it (moonlight-android MediaCodecHelper).
        decOperatingRate = p.getBoolean(KEY_DEC_OPERATING_RATE, metaHeadset);
        decPreferLowLatencyComponent = p.getBoolean(KEY_DEC_PREFER_LOW_LATENCY_COMPONENT, false);
        auAggregation = p.getBoolean(KEY_AU_AGGREGATION, false);
        decDebugKeyMask = p.getInt(KEY_DEC_DEBUG_KEY_MASK, -1);
        decComponent = p.getString(KEY_DEC_COMPONENT, "");
        xrRefreshHz = validRefresh(p.getInt(KEY_XR_REFRESH_HZ, DEFAULT_REFRESH_HZ));
        xrUseTimestamps = p.getBoolean(KEY_XR_USE_TIMESTAMPS, false);
        xrLayerShape = LayerShape.parse(p.getString(KEY_XR_LAYER_SHAPE, LayerShape.QUAD.prefValue()));
        xrPerfSustainedHigh = p.getBoolean(KEY_XR_PERF_SUSTAINED_HIGH, true);
        xrFovDeg = clamp(p.getFloat(KEY_XR_FOV_DEG, DEFAULT_FOV_DEG), MIN_FOV_DEG, MAX_FOV_DEG, DEFAULT_FOV_DEG);
        xrFlipVertical = p.getBoolean(KEY_XR_FLIP_VERTICAL, true);
        xrThreadHints = p.getBoolean(KEY_XR_THREAD_HINTS, true);
        xrPhaseReport = p.getString(KEY_XR_PHASE_REPORT, "");
        xrLatchToDisplayUs = p.getInt(KEY_XR_LATCH_TO_DISPLAY_US, DEFAULT_LATCH_TO_DISPLAY_US);
    }

    public static LatencyExperiments from(PrefSource source) {
        return from(source, false);
    }

    /** @param metaHeadset device-dependent defaults for Meta Quest headsets (see isMetaHeadset). */
    public static LatencyExperiments from(PrefSource source, boolean metaHeadset) {
        return new LatencyExperiments(new DefaultOnWrongType(source), metaHeadset);
    }

    /** Quest headsets report "Oculus" (older OS) or "Meta" as Build.MANUFACTURER. */
    public static boolean isMetaHeadset(String manufacturer) {
        return "Oculus".equalsIgnoreCase(manufacturer) || "Meta".equalsIgnoreCase(manufacturer);
    }

    /**
     * SharedPreferences throws ClassCastException when a key was stored with another type; a stale
     * or hand-edited pref must fall back to its default instead of killing the activity at start.
     */
    private static final class DefaultOnWrongType implements PrefSource {
        private final PrefSource source;

        DefaultOnWrongType(PrefSource source) {
            this.source = source;
        }

        public boolean getBoolean(String k, boolean d) {
            try { return source.getBoolean(k, d); } catch (ClassCastException e) { return d; }
        }

        public int getInt(String k, int d) {
            try { return source.getInt(k, d); } catch (ClassCastException e) { return d; }
        }

        public float getFloat(String k, float d) {
            try { return source.getFloat(k, d); } catch (ClassCastException e) { return d; }
        }

        public String getString(String k, String d) {
            try { return source.getString(k, d); } catch (ClassCastException e) { return d; }
        }
    }

    public static LatencyExperiments load(Context context) {
        final SharedPreferences sp = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        return from(new PrefSource() {
            public boolean getBoolean(String k, boolean d) { return sp.getBoolean(k, d); }
            public int getInt(String k, int d) { return sp.getInt(k, d); }
            public float getFloat(String k, float d) { return sp.getFloat(k, d); }
            public String getString(String k, String d) { return sp.getString(k, d); }
        }, isMetaHeadset(Build.MANUFACTURER));
    }

    static int validRefresh(int hz) {
        for (int supported : SUPPORTED_REFRESH_HZ) {
            if (supported == hz) return hz;
        }
        return DEFAULT_REFRESH_HZ;
    }

    static float clamp(float value, float lo, float hi, float def) {
        if (Float.isNaN(value)) return def;
        return Math.max(lo, Math.min(hi, value));
    }

    /** Compact description of the active levers, for the stats panel and measurement logs. */
    public String summary() {
        StringBuilder dec = new StringBuilder();
        if (lowLatencyDecoder) dec.append("LL ");
        if (decPictureOrder) dec.append("PO ");
        if (decOperatingRate) dec.append("OR ");
        if (decPreferLowLatencyComponent) dec.append("LLC ");
        if (auAggregation) dec.append("AU ");
        String decoder = dec.length() == 0 ? "stock" : dec.toString().trim();
        StringBuilder xr = new StringBuilder();
        xr.append(xrRefreshHz).append("Hz ").append(xrLayerShape.prefValue());
        if (xrUseTimestamps) xr.append(" TS");
        if (xrPerfSustainedHigh) xr.append(" perf");
        if (xrThreadHints) xr.append(" hints");
        if (xrFlipVertical) xr.append(" flip");
        return decoder + " | " + xr;
    }
}
