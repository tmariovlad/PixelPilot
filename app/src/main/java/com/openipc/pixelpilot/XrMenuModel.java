package com.openipc.pixelpilot;

import static com.openipc.videonative.LatencyExperiments.*;

import com.openipc.videonative.LatencyExperiments;
import com.openipc.xr.PanelMode;
import com.openipc.xr.PresetCatalog;
import com.openipc.xr.menu.MenuModel;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.function.Supplier;

/**
 * The menu's values (docs/xr/menu-design.md): Quest options read through {@link LatencyExperiments} (so a value and
 * its default are the ones the app actually uses), air options from the air's VMODE1 catalog, the stats panel from
 * {@link PanelMode}. Radio, codec and channel stay unavailable until the air lists them (§7).
 */
final class XrMenuModel implements MenuModel {
    /** The keyframe-interval choices; "default" removes the pref, so the native default applies (IdrRequestPolicy.h). */
    static final List<String> IDR_INTERVALS =
            Collections.unmodifiableList(Arrays.asList("default", "100", "200", "300", "500", "1000", "2000"));
    static final List<String> SHAPES = Collections.unmodifiableList(Arrays.asList(
            LayerShape.QUAD.prefValue(), LayerShape.CYLINDER.prefValue()));

    private final Supplier<LatencyExperiments> experiments;
    private final Supplier<PresetCatalog> catalog;
    private final Supplier<String> panelMode;

    XrMenuModel(Supplier<LatencyExperiments> experiments, Supplier<PresetCatalog> catalog, Supplier<String> panelMode) {
        this.experiments = experiments;
        this.catalog = catalog;
        this.panelMode = panelMode;
    }

    @Override
    public String value(String id) {
        PresetCatalog c = catalog.get();
        switch (id) {
            case XrMenuTree.AIR_MODE:
                return c == null ? null : c.activeMode;
            case XrMenuTree.AIR_QUALITY:
                return c == null ? null : Integer.toString(c.requestedKbps);
            case XrMenuTree.PANEL_DETAIL:
                return panelMode.get();
            default:
                return quest(id, experiments.get());
        }
    }

    private static String quest(String id, LatencyExperiments e) {
        switch (id) {
            case KEY_FEED_INCOMPLETE_FRAMES: return b(e.feedIncompleteFrames);
            case KEY_REQUEST_IDR_ON_LOSS: return b(e.requestIdrOnLoss);
            case KEY_IDR_MIN_INTERVAL_MS: return e.idrMinIntervalMs > 0 ? Integer.toString(e.idrMinIntervalMs) : "default";
            case KEY_FREEZE_UNTIL_IDR: return b(e.freezeUntilIdr);
            case KEY_RTP_TIGHT_REORDER: return b(e.rtpTightReorder);
            case KEY_LOW_LATENCY_DECODER: return b(e.lowLatencyDecoder);
            case KEY_DEC_PICTURE_ORDER: return b(e.decPictureOrder);
            case KEY_DEC_OPERATING_RATE: return b(e.decOperatingRate);
            case KEY_DEC_PREFER_LOW_LATENCY_COMPONENT: return b(e.decPreferLowLatencyComponent);
            case KEY_AU_AGGREGATION: return b(e.auAggregation);
            case KEY_XR_REFRESH_HZ: return Integer.toString(e.xrRefreshHz);
            case KEY_XR_FOV_DEG: return Integer.toString(Math.round(e.xrFovDeg));
            case KEY_XR_LAYER_SHAPE: return e.xrLayerShape.prefValue();
            case KEY_XR_FLIP_VERTICAL: return b(e.xrFlipVertical);
            case KEY_XR_USE_TIMESTAMPS: return b(e.xrUseTimestamps);
            case KEY_XR_PERF_SUSTAINED_HIGH: return b(e.xrPerfSustainedHigh);
            case KEY_XR_THREAD_HINTS: return b(e.xrThreadHints);
            default: return null;
        }
    }

    @Override
    public List<String> choices(String id) {
        PresetCatalog c = catalog.get();
        switch (id) {
            case KEY_IDR_MIN_INTERVAL_MS:
                return IDR_INTERVALS;
            case KEY_XR_REFRESH_HZ: {
                List<String> out = new ArrayList<>();
                for (int hz : SUPPORTED_REFRESH_HZ) out.add(Integer.toString(hz));
                return out;
            }
            case KEY_XR_LAYER_SHAPE:
                return SHAPES;
            case XrMenuTree.PANEL_DETAIL:
                return PanelMode.NAMES;
            case XrMenuTree.AIR_MODE: {
                if (c == null) return null;
                List<String> out = new ArrayList<>();
                for (PresetCatalog.Mode m : c.modes) out.add(m.name);
                return out;
            }
            case XrMenuTree.AIR_QUALITY: {
                if (c == null) return null;
                List<String> out = new ArrayList<>();
                for (PresetCatalog.Quality q : c.qualities) out.add(Integer.toString(q.kbps));
                return out;
            }
            default:
                return null;
        }
    }

    @Override
    public boolean available(String id) {
        switch (id) {
            case XrMenuTree.AIR_MODE:
            case XrMenuTree.AIR_QUALITY:
                return catalog.get() != null;
            case XrMenuTree.AIR_MCS:
            case XrMenuTree.AIR_FEC:
            case XrMenuTree.AIR_STREAMS:
            case XrMenuTree.AIR_TXPOWER:
            case XrMenuTree.AIR_ALINK:
            case XrMenuTree.AIR_CODEC:
            case XrMenuTree.AIR_CHANNEL:
                return false;   // needs the VMODE1 radio fields (docs/xr/menu-design.md §7)
            default:
                return true;
        }
    }

    private static String b(boolean v) {
        return Boolean.toString(v).toLowerCase(Locale.US);
    }
}
