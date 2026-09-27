package com.openipc.xr;

import java.util.Locale;

/**
 * The preset menu on the stats panel, driven by the thumbsticks (docs/xr/presets-design.md). Left/right picks the
 * MODE, up/down the QUALITY; holding the thumbstick click {@link #HOLD_APPLY_MS} applies what is highlighted, and
 * holding it {@link #HOLD_SAVE_MS} on the active choice saves it as the air unit's default. Nothing is applied without
 * the hold. The first flick only opens the menu. Pure logic with an injected clock; UI thread only.
 */
public final class PresetMenu {
    public static final long HOLD_APPLY_MS = 1000;
    public static final long HOLD_SAVE_MS = 3000;
    public static final long IDLE_CLOSE_MS = 6000;
    static final String SWITCH_WARNING = "switch ~10-14 s, picture frozen ~4 s";

    /** What the pilot confirmed. {@code mode} is null and {@code kbps} 0 for an axis that does not change. */
    public static final class Action {
        public final String mode;
        public final int kbps;
        public final boolean saveDefault;

        Action(String mode, int kbps, boolean saveDefault) {
            this.mode = mode;
            this.kbps = kbps;
            this.saveDefault = saveDefault;
        }
    }

    private static final int STICK = XrBridge.INPUT_STICK_LEFT | XrBridge.INPUT_STICK_RIGHT | XrBridge.INPUT_STICK_UP
            | XrBridge.INPUT_STICK_DOWN;

    private PresetCatalog catalog;
    private boolean open;
    private int mode, quality;        // highlighted indices
    private long lastInputMs;
    private long pressMs = -1;        // thumbstick click held since, or -1
    private boolean fired;            // the current hold already did something

    /** A new list or state from the air. The highlight is kept while the menu is open. */
    public void setCatalog(PresetCatalog c) {
        catalog = c;
        if (!open) highlightActive();
    }

    public boolean isOpen() {
        return open;
    }

    /** The input bits meant for the rest of the panel: B/Y closes an open menu instead of hiding the panel. */
    public int passThrough(int events) {
        return open ? events & ~XrBridge.INPUT_PANEL_VISIBILITY : events;
    }

    /** Applies the input bits of one stats tick. Returns what to send to the air, or null. */
    public Action update(int events, long nowMs) {
        if ((events & STICK) != 0) {
            lastInputMs = nowMs;
            if (!open) {
                open = true;
                highlightActive();
            } else if (catalog != null) {
                if ((events & XrBridge.INPUT_STICK_LEFT) != 0) mode = step(mode, -1, catalog.modes.size());
                if ((events & XrBridge.INPUT_STICK_RIGHT) != 0) mode = step(mode, 1, catalog.modes.size());
                if ((events & XrBridge.INPUT_STICK_UP) != 0) quality = step(quality, 1, catalog.qualities.size());
                if ((events & XrBridge.INPUT_STICK_DOWN) != 0) quality = step(quality, -1, catalog.qualities.size());
            }
        }
        if (open && (events & XrBridge.INPUT_PANEL_VISIBILITY) != 0) close();
        if (open && (events & XrBridge.INPUT_STICK_PRESS) != 0) {
            pressMs = nowMs;
            fired = false;
            lastInputMs = nowMs;
        }
        Action action = null;
        if (open && pressMs >= 0 && !fired && catalog != null && !catalog.modes.isEmpty()) {
            boolean changes = modeChanges() || qualityChanges();
            long held = nowMs - pressMs;
            if (changes && held >= HOLD_APPLY_MS) {
                action = new Action(modeChanges() ? modeAt(mode).name : null,
                        qualityChanges() ? catalog.qualities.get(quality).kbps : 0, false);
            } else if (!changes && held >= HOLD_SAVE_MS) {
                action = new Action(null, 0, true);
            }
            if (action != null) close();
        }
        if ((events & XrBridge.INPUT_STICK_RELEASE) != 0) pressMs = -1;
        if (open && pressMs < 0 && nowMs - lastInputMs >= IDLE_CLOSE_MS) close();
        return action;
    }

    /** The menu lines (put above the stats lines), empty when closed. Each fits the ~60-column panel. */
    public String[] lines(boolean armed, long nowMs) {
        if (!open) return new String[0];
        if (catalog == null || catalog.modes.isEmpty()) {
            return new String[]{"PRESETS  no list from the air unit yet"};
        }
        PresetCatalog.Mode m = modeAt(mode);
        String modeLine = String.format(Locale.US, "MODE < %s >  %s%s", m.label, m.desc, modeChanges() ? "" : "  (active)");
        String info = String.format(Locale.US, "  FOV %s %%  G2G %s ms", m.fov, m.g2g);
        String qualityLine;
        if (catalog.qualities.isEmpty()) {
            qualityLine = "QUALITY  -";
        } else {
            PresetCatalog.Quality q = catalog.qualities.get(quality);
            qualityLine = String.format(Locale.US, "QUALITY ^ %s v  est. +%s ms%s", mbit(q.kbps), q.costMs,
                    qualityChanges() ? "" : "  (active)");
        }
        String hint;
        if (pressMs >= 0 && !fired) {
            hint = String.format(Locale.US, "holding %.1f s", (nowMs - pressMs) / 1000.0);
        } else if (modeChanges()) {
            hint = "hold stick 1 s: " + SWITCH_WARNING;
        } else if (qualityChanges()) {
            hint = "hold stick 1 s to apply";
        } else {
            hint = "hold stick 3 s: save as default";
        }
        if (armed) hint += "  ARMED";
        return new String[]{modeLine, info, qualityLine, hint};
    }

    /** "4 Mbit", "2.5 Mbit". */
    public static String mbit(int kbps) {
        return kbps % 1000 == 0 ? (kbps / 1000) + " Mbit" : String.format(Locale.US, "%.1f Mbit", kbps / 1000.0);
    }

    private void close() {
        open = false;
        fired = true;      // a hold that closed the menu must not fire again
        pressMs = -1;
    }

    private void highlightActive() {
        if (catalog == null) return;
        mode = Math.max(0, catalog.modeIndex(catalog.activeMode));
        quality = Math.max(0, catalog.qualityIndex(catalog.requestedKbps));
    }

    private boolean modeChanges() {
        return catalog != null && !catalog.modes.isEmpty() && !modeAt(mode).name.equals(catalog.activeMode);
    }

    private boolean qualityChanges() {
        return catalog != null && !catalog.qualities.isEmpty()
                && catalog.qualities.get(quality).kbps != catalog.requestedKbps;
    }

    private PresetCatalog.Mode modeAt(int i) {
        return catalog.modes.get(Math.min(i, catalog.modes.size() - 1));
    }

    private static int step(int i, int d, int n) {
        return n == 0 ? 0 : Math.max(0, Math.min(n - 1, i + d));
    }
}
