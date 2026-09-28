package com.openipc.pixelpilot;

import static com.openipc.videonative.LatencyExperiments.*;

import com.openipc.xr.menu.ApplyClass;
import com.openipc.xr.menu.MenuAction;
import com.openipc.xr.menu.MenuItem;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/**
 * Carries out what the pilot confirmed in the menu (docs/xr/menu-design.md §4): a Quest option is written to the prefs
 * with the type {@link com.openipc.videonative.LatencyExperiments} reads, then applied live or by a relaunch per its
 * {@link ApplyClass}; an air option goes to the VMODE1 session. The side effects go through {@link Effects}.
 */
final class XrMenuActions {
    /** The activity's side of the menu. */
    interface Effects {
        void putBoolean(String key, boolean value);
        void putInt(String key, int value);
        void putFloat(String key, float value);
        void putString(String key, String value);
        void remove(String key);
        /** Re-read the prefs and apply every live lever (stream levers, layout). */
        void applyLive();
        /** Restart the XR activity so start-time levers take effect. */
        void relaunch();
        void setPanelMode(String mode);
        /** A VMODE1 apply: {@code mode} null / {@code kbps} 0 leave that axis alone. */
        void airApply(String mode, int kbps);
        void airSaveDefault();
    }

    /** The Quest keys the menu owns; "Quest to defaults" removes exactly these. */
    static final List<String> QUEST_KEYS = Collections.unmodifiableList(Arrays.asList(
            KEY_FEED_INCOMPLETE_FRAMES, KEY_REQUEST_IDR_ON_LOSS, KEY_IDR_MIN_INTERVAL_MS, KEY_FREEZE_UNTIL_IDR,
            KEY_RTP_TIGHT_REORDER, KEY_LOW_LATENCY_DECODER, KEY_DEC_PICTURE_ORDER, KEY_DEC_OPERATING_RATE,
            KEY_DEC_PREFER_LOW_LATENCY_COMPONENT, KEY_AU_AGGREGATION, KEY_XR_REFRESH_HZ, KEY_XR_FOV_DEG,
            KEY_XR_LAYER_SHAPE, KEY_XR_FLIP_VERTICAL, KEY_XR_USE_TIMESTAMPS, KEY_XR_PERF_SUSTAINED_HIGH,
            KEY_XR_THREAD_HINTS));

    private final Effects fx;

    XrMenuActions(Effects fx) {
        this.fx = fx;
    }

    void run(MenuAction a) {
        if (a == null) return;
        MenuItem it = a.item;
        switch (a.type) {
            case SET:
                if (XrMenuTree.PANEL_DETAIL.equals(it.id)) {
                    fx.setPanelMode(a.value);
                    return;
                }
                write(it, a.value);
                if (it.apply == ApplyClass.RELAUNCH) fx.relaunch();
                else fx.applyLive();
                return;
            case APPLY_AIR:
                if (XrMenuTree.AIR_MODE.equals(it.id)) fx.airApply(a.value, 0);
                else if (XrMenuTree.AIR_QUALITY.equals(it.id)) fx.airApply(null, Integer.parseInt(a.value));
                return;
            case SAVE_AIR_DEFAULT:
                fx.airSaveDefault();
                return;
            case RUN:
                if (XrMenuTree.RESET_QUEST.equals(it.id)) {
                    for (String k : QUEST_KEYS) fx.remove(k);
                    fx.relaunch();
                }
                return;
            default:
        }
    }

    /** The pref type per key, as LatencyExperiments reads it. */
    private void write(MenuItem it, String v) {
        switch (it.id) {
            case KEY_IDR_MIN_INTERVAL_MS:
                if ("default".equals(v)) fx.remove(it.id);
                else fx.putInt(it.id, Integer.parseInt(v));
                return;
            case KEY_XR_REFRESH_HZ:
                fx.putInt(it.id, Integer.parseInt(v));
                return;
            case KEY_XR_FOV_DEG:
                fx.putFloat(it.id, Float.parseFloat(v));
                return;
            case KEY_XR_LAYER_SHAPE:
                fx.putString(it.id, v);
                return;
            default:
                if (it.kind == MenuItem.Kind.BOOL) fx.putBoolean(it.id, Boolean.parseBoolean(v));
                else throw new IllegalArgumentException("no pref type for " + it.id);
        }
    }
}
