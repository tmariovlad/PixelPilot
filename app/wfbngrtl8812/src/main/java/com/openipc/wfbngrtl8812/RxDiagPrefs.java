package com.openipc.wfbngrtl8812;

import java.util.Map;

/**
 * Link-audit RX diagnostics (T6 of the 25 Mbit/s link audit), read from the app's "general" preferences when the
 * link starts. All off by default, so the default RX path is unchanged. A test script switches them with one prefs
 * write and an app restart (like scripts/quest/set_bw.py does for the bandwidth), no rebuild:
 * <ul>
 *   <li>{@code rx-diag-ring-ms} (int): devourer RX ring telemetry cadence in ms, 0 = off. The ring counters go to the
 *   trace as ppxr_usb_* (starvation, host drops).</li>
 *   <li>{@code rx-diag-keep-corrupted} (boolean): let frames that failed FCS/ICV reach the host; they are counted as
 *   ppxr_rx_crc_err / ppxr_rx_icv_err (RF bit errors) and then dropped, so every other counter is unchanged.</li>
 *   <li>{@code rx-diag-mode} (string): devourer RX mode, "async" (default), "spsc" (spsc-fat) or "reorder".</li>
 * </ul>
 * Native side: WfbngLink::RxDiagConfig / RxDiag.h.
 */
public final class RxDiagPrefs {
    public static final String KEY_RING_MS = "rx-diag-ring-ms";
    public static final String KEY_KEEP_CORRUPTED = "rx-diag-keep-corrupted";
    public static final String KEY_MODE = "rx-diag-mode";

    // Must match WfbngLink::RxDiagConfig::rx_mode.
    public static final int MODE_ASYNC = 0;
    public static final int MODE_SPSC = 1;
    public static final int MODE_REORDER = 2;

    public static final int MAX_RING_MS = 10000;

    public final int ringMs;
    public final boolean keepCorrupted;
    public final int rxMode;

    public RxDiagPrefs(int ringMs, boolean keepCorrupted, int rxMode) {
        this.ringMs = ringMs;
        this.keepCorrupted = keepCorrupted;
        this.rxMode = rxMode;
    }

    public boolean enabled() {
        return ringMs > 0 || keepCorrupted || rxMode != MODE_ASYNC;
    }

    /** From SharedPreferences.getAll(); a missing key or a value of the wrong type means off. */
    public static RxDiagPrefs fromPrefs(Map<String, ?> prefs) {
        Object ring = prefs.get(KEY_RING_MS);
        Object keep = prefs.get(KEY_KEEP_CORRUPTED);
        Object mode = prefs.get(KEY_MODE);
        int ringMs = ring instanceof Integer ? Math.max(0, Math.min(MAX_RING_MS, (Integer) ring)) : 0;
        boolean keepCorrupted = keep instanceof Boolean && (Boolean) keep;
        int rxMode = MODE_ASYNC;
        if ("spsc".equals(mode)) {
            rxMode = MODE_SPSC;
        } else if ("reorder".equals(mode)) {
            rxMode = MODE_REORDER;
        }
        return new RxDiagPrefs(ringMs, keepCorrupted, rxMode);
    }
}
